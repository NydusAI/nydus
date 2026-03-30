"""8-phase spawning pipeline.

Symmetric boundaries — secrets cross at the file level:

1. Parse         — Resolve FROM, SOURCEs, base egg
2. Read          — Read all source files into dict[str, str]
3. Credential scan — Replace credential values with {{SECRET_NNN}}
4. PII redact    — Replace PII with {{PII_NNN}} via Presidio
5. Parse         — spawner.parse(redacted_files) -> ParseResult
6. Build records — RawSkill/RawMemory -> SkillRecord/MemoryRecord
7. LLM Refine    — Deduplicate memory, clean skills (on redacted text)
8. Filter + Package — Bucket filter, label overrides, Manifest + Egg
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pynydus
from pynydus.api.errors import ConnectorError
from pynydus.api.raw_types import ParseResult
from pynydus.api.schemas import (
    Bucket,
    Egg,
    EggPartial,
    InjectionMode,
    Manifest,
    McpServerConfig,
    MemoryLabel,
    MemoryModule,
    MemoryRecord,
    RedactionPolicy,
    RedactMode,
    SecretKind,
    SecretRecord,
    SecretsModule,
    SkillRecord,
    SkillsModule,
    SourceEntry,
    SourceType,
)
from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective

if TYPE_CHECKING:
    from pynydus.pkg.llm import NydusLLMConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline context
# ---------------------------------------------------------------------------


@dataclass
class PipelineContext:
    """Mutable context passed through each pipeline phase."""

    source_path: Path
    source_type: SourceType | None = None
    nydusfile_config: NydusfileConfig | None = None
    nydusfile_dir: Path | None = None
    redact_mode: RedactMode = RedactMode.PII
    llm_config: NydusLLMConfig | None = None
    spawn_log: list[dict] = field(default_factory=list)


def _resolve_source_entry_path(path_str: str, nydusfile_dir: Path | None) -> Path:
    """Resolve a path from a Nydusfile SOURCE (or similar) entry."""
    expanded = Path(path_str).expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    if nydusfile_dir is not None:
        return (nydusfile_dir / path_str).resolve()
    return Path(path_str)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build(
    source_path: str | Path,
    *,
    source_type: str | None = None,
    nydusfile_config: NydusfileConfig | None = None,
    redact_mode: RedactMode | None = None,
    llm_config: NydusLLMConfig | None = None,
    nydusfile_dir: Path | None = None,
) -> tuple[Egg, dict[str, str], dict[str, list[dict]]]:
    """Run the full 8-phase spawning pipeline.

    Secrets cross the boundary at the file level:
    - Phase 3-4 (secrets OUT): real values -> {{SECRET_NNN}} / {{PII_NNN}}
    - Spawner only sees redacted content
    - LLM only sees redacted content

    Returns
    -------
    tuple[Egg, dict[str, str], dict[str, list[dict]]]
        ``(egg, raw_artifacts, logs)`` — the built Egg, a dict of redacted
        source file contents, and a dict of pipeline log entries.
    """
    source_path = Path(source_path)
    config = nydusfile_config

    nydusfile_dir_path = Path(nydusfile_dir).resolve() if nydusfile_dir is not None else None

    ctx = PipelineContext(
        source_path=source_path,
        nydusfile_config=config,
        nydusfile_dir=nydusfile_dir_path,
        redact_mode=redact_mode or (config.redact if config else RedactMode.PII),
        llm_config=llm_config,
    )

    # --- Phase 1: Parse Nydusfile ---
    resolved_source, base_partial = _phase1_parse(ctx, source_type)
    ctx.source_type = resolved_source

    if base_partial is not None:
        # Base-egg inheritance: already has typed records, skip extraction
        skills_module = base_partial.skills
        memory_module = base_partial.memory
        secrets_module = base_partial.secrets

        effective_buckets = config.effective_buckets if config else set(Bucket)
        skills_module, memory_module, secrets_module = _apply_bucket_filter(
            skills_module, memory_module, secrets_module, effective_buckets
        )
        if config and config.custom_labels:
            _apply_custom_labels(memory_module, config.custom_labels)
        egg = _phase8_package(
            ctx, resolved_source, skills_module, memory_module, secrets_module,
            base_partial.source_metadata, effective_buckets,
        )
        if config and config.secret_policy != "default":
            _apply_secret_policy(egg, config.secret_policy)
        logs = {"spawn_log": ctx.spawn_log}
        return egg, base_partial.raw_artifacts, logs

    # --- Phase 2: Read source files ---
    spawner = _get_spawner(resolved_source)
    files = _phase2_read_files(ctx, spawner)

    # Filter out excluded files/patterns
    if config and config.exclude_files:
        files = _filter_files_by_patterns(files, config.exclude_files)

    # --- Phase 3: Secrets OUT boundary, part 1 (credential scan) ---
    # Credential scanning always runs unless redaction is fully disabled.
    cred_secrets: list[SecretRecord] = []
    if ctx.redact_mode != RedactMode.NONE:
        files, cred_secrets = _phase3_scan_credentials(files, ctx)

    # --- Phase 4: Secrets OUT boundary, part 2 (PII redact) ---
    pii_secrets: list[SecretRecord] = []
    if ctx.redact_mode in (RedactMode.PII, RedactMode.ALL):
        files, pii_secrets = _phase4_redact_pii(files, ctx)

    # After this point, `files` is fully "raw" — no real secrets or PII remain.

    # --- Phase 5: Parse (spawner clean room) ---
    parse_result = _phase5_parse(spawner, files, ctx)

    # --- Phase 6: Build records ---
    skills_module = _build_skills_module_from_parse(parse_result, resolved_source.value, ctx)
    memory_module = _build_memory_module_from_parse(parse_result, resolved_source.value, ctx)

    # Merge credential + PII secrets
    all_secrets = cred_secrets + pii_secrets
    seen_placeholders: set[str] = set()
    deduped_secrets: list[SecretRecord] = []
    for s in all_secrets:
        if s.placeholder not in seen_placeholders:
            deduped_secrets.append(s)
            seen_placeholders.add(s.placeholder)
    secrets_module = SecretsModule(secrets=deduped_secrets)

    # --- Phase 7: LLM Refine (on redacted content) ---
    if ctx.llm_config is not None:
        from pynydus.engine.refinement import refine_memory, refine_skills

        if skills_module.skills:
            skills_module = refine_skills(skills_module, ctx.llm_config, spawn_log=ctx.spawn_log)
        if memory_module.memory:
            memory_module = refine_memory(memory_module, ctx.llm_config, spawn_log=ctx.spawn_log)

    # --- Phase 8: Filter + Package ---
    effective_buckets = config.effective_buckets if config else set(Bucket)
    skills_module, memory_module, secrets_module = _apply_bucket_filter(
        skills_module, memory_module, secrets_module, effective_buckets
    )

    if config and config.custom_labels:
        _apply_custom_labels(memory_module, config.custom_labels)

    source_metadata = parse_result.source_metadata or {"source_dir": str(ctx.source_path)}

    egg = _phase8_package(
        ctx, resolved_source, skills_module, memory_module, secrets_module,
        source_metadata, effective_buckets,
    )

    if config and config.secret_policy != "default":
        _apply_secret_policy(egg, config.secret_policy)

    logs = {"spawn_log": ctx.spawn_log}
    return egg, files, logs


# ---------------------------------------------------------------------------
# Phase 1: Parse
# ---------------------------------------------------------------------------


def _phase1_parse(
    ctx: PipelineContext, explicit_source: str | None
) -> tuple[SourceType, EggPartial | None]:
    """Resolve source type and base egg."""
    config = ctx.nydusfile_config
    base_partial = None

    if config and config.base_egg:
        from pynydus.engine.merger import load_base_egg, merge

        base_ref = config.base_egg
        if _is_registry_ref(base_ref):
            base_ref = _pull_registry_egg(base_ref)
        else:
            p = Path(base_ref).expanduser()
            if not p.is_absolute() and ctx.nydusfile_dir is not None:
                base_ref = str((ctx.nydusfile_dir / base_ref).resolve())

        base = load_base_egg(base_ref)
        resolved_source = base.manifest.source_type
        base_partial = merge(base, config.merge_ops)
        base_partial.source_metadata["base_egg"] = config.base_egg
    else:
        resolved_source = _resolve_source_type(ctx.source_path, explicit_source, config)

    return resolved_source, base_partial


def _resolve_source_type(
    source_path: Path, explicit: str | None, config: NydusfileConfig | None
) -> SourceType:
    """Determine source type from explicit flag, config, or auto-detection."""
    if explicit:
        try:
            return SourceType(explicit)
        except ValueError:
            raise ConnectorError(f"Unknown source type: {explicit}")
    if config:
        return config.source
    return _auto_detect(source_path)


def _auto_detect(source_path: Path) -> SourceType:
    """Auto-detect the source type from the input path."""
    from pynydus.agents.openclaw.spawner import OpenClawSpawner

    if OpenClawSpawner().detect(source_path):
        return SourceType.OPENCLAW

    from pynydus.agents.letta.spawner import LettaSpawner

    if LettaSpawner().detect(source_path):
        return SourceType.LETTA

    raise ConnectorError(
        f"Cannot auto-detect source type for: {source_path}. "
        f"Add a SOURCE directive to your Nydusfile."
    )


# ---------------------------------------------------------------------------
# Phase 2: Read source files
# ---------------------------------------------------------------------------


def _phase2_read_files(ctx: PipelineContext, spawner: object) -> dict[str, str]:
    """Read all source files into a dict using spawner's FILE_PATTERNS."""
    config = ctx.nydusfile_config
    files: dict[str, str] = {}

    source_paths: list[tuple[Path, str | None]] = []

    if config and config.sources:
        for src in config.sources:
            resolved = _resolve_source_entry_path(src.path, ctx.nydusfile_dir)
            source_paths.append((resolved, src.source_type))
    else:
        source_paths.append((ctx.source_path, None))

    for src_path, src_type in source_paths:
        if src_type:
            s = _get_spawner(SourceType(src_type))
        else:
            s = spawner
        patterns = getattr(s, "FILE_PATTERNS", ["*.md", "*.json", "*.yaml", "*.yml", "*.txt"])
        files.update(_read_files_from_path(src_path, patterns))

    return files


def _read_files_from_path(root: Path, patterns: list[str]) -> dict[str, str]:
    """Read text files matching patterns from a directory."""
    result: dict[str, str] = {}
    if not root.is_dir():
        return result

    for pattern in patterns:
        if "/" in pattern:
            # Subdirectory pattern like "tools/*.py"
            parts = pattern.split("/", 1)
            sub_dir = root / parts[0]
            if sub_dir.is_dir():
                for fpath in sorted(sub_dir.glob(parts[1])):
                    try:
                        result[f"{parts[0]}/{fpath.name}"] = fpath.read_text()
                    except (UnicodeDecodeError, OSError):
                        continue
        else:
            for fpath in sorted(root.glob(pattern)):
                try:
                    result[fpath.name] = fpath.read_text()
                except (UnicodeDecodeError, OSError):
                    continue

    return result


# ---------------------------------------------------------------------------
# Phase 3: Credential scan (secrets OUT, part 1)
# ---------------------------------------------------------------------------


def _phase3_scan_credentials(
    files: dict[str, str], ctx: PipelineContext
) -> tuple[dict[str, str], list[SecretRecord]]:
    """Replace credential values with {{SECRET_NNN}} placeholders."""
    from pynydus.pkg.credential_scanner import scan_credentials

    redacted, secrets = scan_credentials(files, start_index=1)

    for s in secrets:
        ctx.spawn_log.append({
            "type": "credential_scan",
            "source": s.occurrences[0] if s.occurrences else "unknown",
            "placeholder": s.placeholder,
            "name": s.name,
        })

    return redacted, secrets


# ---------------------------------------------------------------------------
# Phase 4: PII redact (secrets OUT, part 2)
# ---------------------------------------------------------------------------


def _phase4_redact_pii(
    files: dict[str, str], ctx: PipelineContext
) -> tuple[dict[str, str], list[SecretRecord]]:
    """Replace PII with {{PII_NNN}} placeholders via Presidio."""
    from pynydus.pkg.presidio import PIIRedactor

    redactor = PIIRedactor(start_index=1)
    pii_secrets: list[SecretRecord] = []
    redacted: dict[str, str] = {}

    for fname, content in files.items():
        result = redactor.redact(content)
        redacted[fname] = result.redacted_text
        for repl in result.replacements:
            pii_secrets.append(
                SecretRecord(
                    id=f"pii_{repl.placeholder.strip('{}').split('_')[1]}".lower(),
                    placeholder=repl.placeholder,
                    kind=SecretKind.PII,
                    pii_type=repl.pii_type,
                    name=f"PII_{repl.pii_type}",
                    required_at_hatch=False,
                    injection_mode=InjectionMode.SUBSTITUTION,
                    description=f"Redacted {repl.pii_type}",
                )
            )
            ctx.spawn_log.append({
                "type": "redaction",
                "source": f"file:{fname}",
                "pii_type": repl.pii_type,
                "placeholder": repl.placeholder,
            })

    return redacted, pii_secrets


# ---------------------------------------------------------------------------
# Phase 5: Parse (spawner clean room)
# ---------------------------------------------------------------------------


def _phase5_parse(
    spawner: object, files: dict[str, str], ctx: PipelineContext
) -> ParseResult:
    """Call spawner.parse() on pre-redacted file contents."""
    if hasattr(spawner, "parse"):
        return spawner.parse(files)  # type: ignore[union-attr]
    # Fallback for legacy spawners without parse()
    raise ConnectorError(f"Spawner {type(spawner).__name__} does not implement parse()")


# ---------------------------------------------------------------------------
# Phase 6: Build records
# ---------------------------------------------------------------------------


def _build_skills_module_from_parse(
    parse_result: ParseResult, source_type: str, ctx: PipelineContext
) -> SkillsModule:
    """Convert ParseResult skills into SkillRecord objects."""
    skills: list[SkillRecord] = []
    for i, rs in enumerate(parse_result.skills, start=1):
        skills.append(
            SkillRecord(
                id=f"skill_{i:03d}",
                name=rs.name,
                source_type=source_type,
                content=rs.content,
                metadata={"source_file": rs.source_file} if rs.source_file else {},
            )
        )

    mcp_configs = {
        name: McpServerConfig(**cfg) for name, cfg in parse_result.mcp_configs.items()
    }
    return SkillsModule(skills=skills, mcp_configs=mcp_configs)


def _build_memory_module_from_parse(
    parse_result: ParseResult, source_type: str, ctx: PipelineContext
) -> MemoryModule:
    """Convert ParseResult memory into MemoryRecord objects."""
    memory: list[MemoryRecord] = []
    for i, rm in enumerate(parse_result.memory, start=1):
        label = rm.label or MemoryLabel.STATE
        memory.append(
            MemoryRecord(
                id=f"mem_{i:03d}",
                text=rm.text,
                label=label,
                source_framework=source_type,
                source_store=rm.source_file or "unknown",
                skill_ref=rm.skill_ref,
                timestamp=rm.timestamp,
                metadata={"source_file": rm.source_file} if rm.source_file else {},
            )
        )
    return MemoryModule(memory=memory)


# ---------------------------------------------------------------------------
# Exclude-files filter
# ---------------------------------------------------------------------------


def _filter_files_by_patterns(files: dict[str, str], patterns: list[str]) -> dict[str, str]:
    """Remove files whose names match any exclude glob."""
    import fnmatch

    def _matches(name: str) -> bool:
        return any(fnmatch.fnmatch(name, pat) for pat in patterns)

    return {k: v for k, v in files.items() if not _matches(k)}


# ---------------------------------------------------------------------------
# Phase 8: Filtering, packaging
# ---------------------------------------------------------------------------


def _apply_bucket_filter(
    skills: SkillsModule,
    memory: MemoryModule,
    secrets: SecretsModule,
    buckets: set[Bucket],
) -> tuple[SkillsModule, MemoryModule, SecretsModule]:
    """Remove excluded buckets."""
    if Bucket.SKILLS not in buckets:
        skills = SkillsModule()
    if Bucket.MEMORY not in buckets:
        memory = MemoryModule()
    if Bucket.SECRETS not in buckets:
        secrets = SecretsModule()
    return skills, memory, secrets


def _phase8_package(
    ctx: PipelineContext,
    source_type: SourceType,
    skills: SkillsModule,
    memory: MemoryModule,
    secrets: SecretsModule,
    source_metadata: dict[str, str],
    effective_buckets: set[Bucket],
) -> Egg:
    """Construct the final Egg with manifest."""
    config = ctx.nydusfile_config
    included_modules = [b.value for b in effective_buckets]

    sources: list[SourceEntry] = []
    if config and config.sources:
        for src in config.sources:
            sources.append(SourceEntry(source_type=src.source_type, source_path=src.path))

    manifest = Manifest(
        nydus_version=pynydus.__version__,
        min_nydus_version=pynydus.__version__,
        egg_version=pynydus.EGG_SPEC_VERSION,
        created_at=datetime.now(UTC),
        source_type=source_type,
        included_modules=included_modules,
        redaction_policy=RedactionPolicy(
            pii_redacted=ctx.redact_mode in (RedactMode.PII, RedactMode.ALL),
            secrets_placeholder_only=True,
        ),
        base_egg=config.base_egg if config else None,
        build_intent=config.purpose if config else None,
        source_metadata=source_metadata,
        sources=sources,
    )

    return Egg(
        manifest=manifest,
        skills=skills,
        memory=memory,
        secrets=secrets,
    )


# ---------------------------------------------------------------------------
# Spawner dispatch
# ---------------------------------------------------------------------------


def _get_spawner(source_type: SourceType):  # noqa: ANN202
    """Return the spawner connector for the given source type."""
    if source_type == SourceType.OPENCLAW:
        from pynydus.agents.openclaw.spawner import OpenClawSpawner

        return OpenClawSpawner()

    if source_type == SourceType.LETTA:
        from pynydus.agents.letta.spawner import LettaSpawner

        return LettaSpawner()

    if source_type == SourceType.ZEROCLAW:
        from pynydus.agents.zeroclaw.spawner import ZeroClawSpawner

        return ZeroClawSpawner()

    raise ConnectorError(f"No spawner available for: {source_type}")


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def _is_registry_ref(ref: str) -> bool:
    """Check if a base egg reference looks like a registry ref (name:version)."""
    if ref.endswith(".egg"):
        return False
    if ref.startswith(("./", "/", "\\")):
        return False
    return ":" in ref


def _pull_registry_egg(ref: str) -> str:
    """Pull a registry egg to a temp file and return its path."""
    import tempfile

    from pynydus.api.errors import ConfigError, RegistryError
    from pynydus.pkg.config import load_config
    from pynydus.remote.registry import NestClient

    parts = ref.rsplit(":", 1)
    if len(parts) != 2 or not parts[1]:
        raise RegistryError(f"Invalid registry reference: {ref}. Expected name:version.")

    name, version = parts

    config = load_config()
    if config.registry is None:
        raise ConfigError(
            f"Cannot resolve registry reference '{ref}': "
            "no 'registry' section in config.json."
        )

    client = NestClient(config.registry.url, author=config.registry.author)

    tmp_dir = Path(tempfile.mkdtemp(prefix="nydus_base_"))
    egg_path = tmp_dir / f"{name.replace('/', '_')}_{version}.egg"

    return str(client.pull(name, version=version, output_path=egg_path))


# ---------------------------------------------------------------------------
# Nydusfile helpers
# ---------------------------------------------------------------------------


def _apply_custom_labels(
    memory: MemoryModule, custom_labels: dict[str, str]
) -> None:
    """Override memory record labels based on source_store pattern matching."""
    import fnmatch

    for rec in memory.memory:
        if not rec.source_store:
            continue
        for pattern, label_str in custom_labels.items():
            if fnmatch.fnmatch(rec.source_store, pattern):
                try:
                    rec.label = MemoryLabel(label_str)
                except ValueError:
                    logger.warning("Unknown label '%s' in LABEL directive, ignoring", label_str)
                break


def _apply_secret_policy(egg: Egg, policy: str) -> None:
    """Override required_at_hatch on all secrets based on policy."""
    required = policy == "all_required"
    for secret in egg.secrets.secrets:
        secret.required_at_hatch = required
