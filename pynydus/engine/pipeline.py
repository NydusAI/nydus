"""Spawning pipeline.

Resolves Nydusfile directives, loads sources, runs gitleaks and Presidio on file
text, invokes the platform spawner, optionally runs LLM refinement, then
builds manifest and ``Egg`` records.

Pipeline steps:
    1. Resolve base egg (FROM directive)
    2. Read source files
    3. Redaction (file filtering, secret scan, PII redaction)
    4. Parse sources via spawner connector
    5. Build structured records (skills, memory, secrets)
    6. Merge with base egg (FROM + SOURCE)
    7. LLM refinement (optional)
    8. Post-processing (custom labels, memory exclusions)
    9. Package egg
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pynydus
from pynydus.api.errors import ConnectorError, GitleaksNotFoundError, NydusfileError
from pynydus.api.raw_types import ParseResult
from pynydus.api.schemas import (
    AgentSkill,
    Egg,
    EggPartial,
    Manifest,
    McpModule,
    MemoryModule,
    MemoryRecord,
    RedactionPolicy,
    SecretRecord,
    SecretsModule,
    SkillsModule,
    SourceEntry,
)
from pynydus.common.enums import (
    AgentType,
    InjectionMode,
    MemoryLabel,
    SecretKind,
)
from pynydus.engine.nydusfile import (
    MergeOp,
    NydusfileConfig,
    SourceDirective,
)

if TYPE_CHECKING:
    from pynydus.llm import LLMTierConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline context
# ---------------------------------------------------------------------------


@dataclass
class PipelineContext:
    """Mutable context passed through each pipeline phase.

    All Nydusfile fields are front-loaded here at the start of the pipeline.
    No phase should reach back into NydusfileConfig.
    """

    nydusfile_dir: Path

    # From Nydusfile (front-loaded)
    sources: list[SourceDirective] = field(default_factory=list)
    base_egg: str | None = None
    merge_ops: list[MergeOp] = field(default_factory=list)
    redact: bool = True
    excluded_memory_labels: list[MemoryLabel] = field(default_factory=list)
    custom_labels: dict[str, str] = field(default_factory=dict)
    source_remove_globs: list[str] = field(default_factory=list)

    # Resolved at pipeline start
    agent_type: AgentType | None = None

    # Runtime
    llm_config: LLMTierConfig | None = None
    spawn_log: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def spawn(
    config: NydusfileConfig,
    *,
    nydusfile_dir: Path,
    llm_config: LLMTierConfig | None = None,
) -> tuple[Egg, dict[str, str], dict[str, list[dict]]]:
    """Run the spawning pipeline.

    This is the single entry point for spawn: it enforces prerequisites such as
    ``ensure_gitleaks_if_needed`` before any file reads or redaction.

    Args:
        config: Parsed Nydusfile (sources, FROM, merge ops, redaction flags).
        nydusfile_dir: Directory containing the Nydusfile (resolves relative paths).
        llm_config: Optional LLM tier for spawn Step 7 refinement.

    Returns:
        ``(egg, raw_artifacts, logs)``: the spawned Egg, redacted source file
        contents, and pipeline log entries (e.g. ``{"spawn_log": [...]}``).

    Raises:
        NydusfileError: If the Nydusfile is invalid (e.g. multiple SOURCE lines).
        GitleaksNotFoundError: When redaction requires gitleaks but it is missing.
    """
    nydusfile_dir = Path(nydusfile_dir).resolve()
    ensure_gitleaks_if_needed(config)
    if len(config.sources) > 1:
        raise NydusfileError(
            "Only one SOURCE directive is allowed. Combine inputs under one directory "
            "or use separate Nydusfiles."
        )
    ctx = PipelineContext(
        nydusfile_dir=nydusfile_dir,
        sources=config.sources,
        base_egg=config.base_egg,
        merge_ops=config.merge_ops,
        redact=config.redact,
        excluded_memory_labels=config.excluded_memory_labels,
        custom_labels=config.custom_labels,
        source_remove_globs=config.source_remove_globs,
        llm_config=llm_config,
    )

    ctx.spawn_log.append(
        {
            "type": "pipeline_start",
            "source_platform": ctx.sources[0].agent_type if ctx.sources else None,
            "base_egg": ctx.base_egg,
            "redact": ctx.redact,
            "sources": [s.path for s in ctx.sources],
        }
    )

    # Step 1: Resolve base egg (FROM directive)
    base_partial, base_agent_type = _resolve_base_egg(ctx)
    ctx.agent_type = base_agent_type or AgentType(ctx.sources[0].agent_type)

    if base_partial is not None and not ctx.sources:
        # FROM-only (no SOURCE): return the merged base egg directly.
        skills_module = base_partial.skills
        memory_module = base_partial.memory
        secrets_module = base_partial.secrets

        if ctx.custom_labels:
            _apply_custom_labels(memory_module, ctx.custom_labels, spawn_log=ctx.spawn_log)
        if ctx.excluded_memory_labels:
            memory_module = _drop_memory_records_with_excluded_labels(
                memory_module, ctx.excluded_memory_labels, spawn_log=ctx.spawn_log
            )
        egg = _package_egg(
            ctx,
            skills_module,
            base_partial.mcp,
            memory_module,
            secrets_module,
        )
        egg = _generate_standards_artifacts(egg, [], ctx)
        logs = {"spawn_log": ctx.spawn_log}
        return egg, base_partial.raw_artifacts, logs

    # Step 2: Read source files
    groups = _read_source_files(ctx)

    # Step 3: Redaction (file filtering, secret scan, PII)
    secret_counter = 1
    pii_counter = 1
    all_secret_records: list[SecretRecord] = []
    all_pii_records: list[SecretRecord] = []

    for i, (src_type, _source_root, group_files) in enumerate(groups):
        if ctx.source_remove_globs:
            before_keys = set(group_files.keys())
            group_files = _filter_files_by_patterns(group_files, ctx.source_remove_globs)
            removed = sorted(before_keys - set(group_files.keys()))
            if removed:
                ctx.spawn_log.append(
                    {
                        "type": "files_removed",
                        "patterns": ctx.source_remove_globs,
                        "removed": removed,
                        "remaining": len(group_files),
                    }
                )

        if ctx.redact:
            group_files, credential_records, secret_counter = _scan_secrets_gitleaks(
                group_files,
                ctx,
                start_index=secret_counter,
            )
            all_secret_records.extend(credential_records)

            group_files, pii_records, pii_counter = _redact_pii(
                group_files,
                ctx,
                start_index=pii_counter,
            )
            all_pii_records.extend(pii_records)

        groups[i] = (src_type, _source_root, group_files)

    # Step 4: Parse sources via spawner connector
    parse_result = _parse_sources(groups, ctx)

    # Step 5: Build structured records
    skills_module = _build_skills_module_from_parse(parse_result, ctx.agent_type)
    mcp_module = _build_mcp_module_from_parse(parse_result)
    memory_module = _build_memory_module_from_parse(parse_result, ctx.agent_type)

    ctx.spawn_log.append(
        {
            "type": "records_built",
            "skills": [
                {
                    "id": s.metadata.get("id", ""),
                    "name": s.name,
                    "source_file": s.metadata.get("source_file"),
                }
                for s in skills_module.skills
            ],
            "memory": [
                {
                    "id": m.id,
                    "label": m.label.value,
                    "source_store": m.source_store,
                    "text_length": len(m.text),
                }
                for m in memory_module.memory
            ],
        }
    )

    all_redaction_records = all_secret_records + all_pii_records
    seen_placeholders: set[str] = set()
    deduped_secrets: list[SecretRecord] = []
    for s in all_redaction_records:
        if s.placeholder not in seen_placeholders:
            deduped_secrets.append(s)
            seen_placeholders.add(s.placeholder)
    secrets_module = SecretsModule(secrets=deduped_secrets)

    # Step 6: Merge with base egg (FROM + SOURCE)
    if base_partial is not None:
        skills_before = len(skills_module.skills)
        memory_before = len(memory_module.memory)
        secrets_before = len(secrets_module.secrets)

        skills_module = _merge_skills(base_partial.skills, skills_module)
        mcp_module = _merge_mcp(base_partial.mcp, mcp_module)
        memory_module = _merge_memory(base_partial.memory, memory_module)
        secrets_module = _merge_secrets(base_partial.secrets, secrets_module)

        ctx.spawn_log.append(
            {
                "type": "base_merge",
                "skills_before": skills_before,
                "skills_after": len(skills_module.skills),
                "memory_before": memory_before,
                "memory_after": len(memory_module.memory),
                "secrets_before": secrets_before,
                "secrets_after": len(secrets_module.secrets),
            }
        )

    # Step 7: LLM refinement (optional)
    if ctx.llm_config is not None:
        from pynydus.engine.refinement import refine_memory, refine_skills

        if skills_module.skills:
            skills_module = refine_skills(skills_module, ctx.llm_config, spawn_log=ctx.spawn_log)
        if memory_module.memory:
            memory_module = refine_memory(memory_module, ctx.llm_config, spawn_log=ctx.spawn_log)

    # Step 8: Post-processing (custom labels, memory exclusions)
    if ctx.custom_labels:
        _apply_custom_labels(memory_module, ctx.custom_labels, spawn_log=ctx.spawn_log)
    if ctx.excluded_memory_labels:
        memory_module = _drop_memory_records_with_excluded_labels(
            memory_module, ctx.excluded_memory_labels, spawn_log=ctx.spawn_log
        )

    # Step 9: Package egg
    egg = _package_egg(
        ctx,
        skills_module,
        mcp_module,
        memory_module,
        secrets_module,
        parse_result=parse_result,
    )

    # Step 10: Generate standards artifacts + stash apm.yml
    egg = _generate_standards_artifacts(egg, groups, ctx)

    raw_artifacts: dict[str, str] = {}
    for _src_type, _root, group_files in groups:
        raw_artifacts.update(group_files)

    logs = {"spawn_log": ctx.spawn_log}
    return egg, raw_artifacts, logs


# ---------------------------------------------------------------------------
# Step 1 helpers: Base egg resolution
# ---------------------------------------------------------------------------


def ensure_gitleaks_if_needed(config: NydusfileConfig) -> None:
    """Raise if gitleaks is required but not installed.

    Secret scanning is required when ``REDACT`` is true (the default) and
    at least one ``SOURCE`` directive is present.  FROM-only spawns and
    ``REDACT false`` pipelines skip file-level scanning entirely.

    Args:
        config: Parsed Nydusfile configuration.

    Raises:
        GitleaksNotFoundError: When scanning is required but gitleaks is not found.
    """
    if not config.redact or not config.sources:
        return

    from pynydus.security.gitleaks import find_gitleaks

    if find_gitleaks() is None:
        raise GitleaksNotFoundError(
            "Secret scanning requires gitleaks but the binary was not found. "
            "Install gitleaks (https://github.com/gitleaks/gitleaks#installing) "
            "or set $NYDUS_GITLEAKS_PATH. To skip scanning, use REDACT false."
        )


def _resolve_base_egg(
    ctx: PipelineContext,
) -> tuple[EggPartial | None, AgentType | None]:
    """If FROM is present, load and merge the base egg.

    Returns ``(partial, agent_type)``: partial is the merged base egg,
    agent_type is the base egg's manifest agent type.
    """
    if not ctx.base_egg:
        return None, None

    from pynydus.engine.merger import load_base_egg, merge

    base_ref = ctx.base_egg
    if _is_registry_ref(base_ref):
        base_ref = _pull_registry_egg(base_ref)
    else:
        p = Path(base_ref).expanduser()
        if not p.is_absolute():
            base_ref = str((ctx.nydusfile_dir / base_ref).resolve())

    base = load_base_egg(base_ref)
    partial = merge(base, ctx.merge_ops, base_dir=ctx.nydusfile_dir)

    ctx.spawn_log.append(
        {
            "type": "base_egg_loaded",
            "ref": ctx.base_egg,
            "agent_type": base.manifest.agent_type,
            "skills": len(partial.skills.skills),
            "memory": len(partial.memory.memory),
            "secrets": len(partial.secrets.secrets),
        }
    )

    return partial, base.manifest.agent_type


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
    from pynydus.config import load_config
    from pynydus.remote.registry import NestClient

    parts = ref.rsplit(":", 1)
    if len(parts) != 2 or not parts[1]:
        raise RegistryError(f"Invalid registry reference: {ref}. Expected name:version.")

    name, version = parts

    config = load_config()
    if config.registry is None:
        raise ConfigError(
            f"Cannot resolve registry reference '{ref}': set NYDUS_REGISTRY_URL "
            "(and optionally NYDUS_REGISTRY_AUTHOR)."
        )

    client = NestClient(config.registry.url, author=config.registry.author)

    tmp_dir = Path(tempfile.mkdtemp(prefix="nydus_base_"))
    egg_path = tmp_dir / f"{name.replace('/', '_')}_{version}.egg"

    return str(client.pull(name, version=version, output_path=egg_path))


# ---------------------------------------------------------------------------
# Step 2 helpers: Source file reading
# ---------------------------------------------------------------------------


def _read_source_files(
    ctx: PipelineContext,
) -> list[tuple[AgentType, Path, dict[str, str]]]:
    """Read source files into independent per-group dicts.

    Returns at most one ``(agent_type, source_root, files)`` tuple (at most one SOURCE).
    Each group's dict has bare filename keys and is independent: no merging
    is performed here.
    """
    groups: list[tuple[AgentType, Path, dict[str, str]]] = []

    for src in ctx.sources:
        expanded = Path(src.path).expanduser()
        resolved = (
            expanded.resolve()
            if expanded.is_absolute()
            else (ctx.nydusfile_dir / src.path).resolve()
        )
        at = AgentType(src.agent_type)
        spawner = _get_spawner(at)
        patterns = getattr(spawner, "FILE_PATTERNS", ["*.md", "*.json", "*.yaml", "*.yml", "*.txt"])
        src_files = _read_files_from_path(resolved, patterns)
        groups.append((at, resolved, src_files))

        ctx.spawn_log.append(
            {
                "type": "source_files_read",
                "agent_type": at.value,
                "path": str(resolved),
                "files": sorted(src_files.keys()),
                "count": len(src_files),
            }
        )

    return groups


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
# Step 3 helpers: Redaction (file filtering, secret scan, PII)
# ---------------------------------------------------------------------------


def _filter_files_by_patterns(files: dict[str, str], patterns: list[str]) -> dict[str, str]:
    """Remove files whose keys match any exclude glob."""
    import fnmatch

    def _matches(name: str) -> bool:
        return any(fnmatch.fnmatch(name, pat) for pat in patterns)

    return {k: v for k, v in files.items() if not _matches(k)}


def _scan_secrets_gitleaks(
    files: dict[str, str],
    ctx: PipelineContext,
    *,
    start_index: int = 1,
) -> tuple[dict[str, str], list[SecretRecord], int]:
    """Replace secrets with ``{{SECRET_NNN}}`` placeholders via gitleaks.

    Writes scannable files to a temp directory, runs gitleaks, maps findings
    back to in-memory dict keys.  Ignored (binary) files pass through
    unchanged.

    Returns ``(redacted_files, credential_records, next_index)``.
    """
    import tempfile

    from pynydus.common.scan_paths import partition_files
    from pynydus.security.gitleaks import apply_gitleaks_findings, run_gitleaks_scan

    scannable, ignored = partition_files(files)

    if not scannable:
        return files, [], start_index

    with tempfile.TemporaryDirectory(prefix="nydus_gl_") as tmp:
        tmp_root = Path(tmp)
        for key, content in scannable.items():
            dest = tmp_root / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")

        findings = run_gitleaks_scan(tmp_root)
        redacted, credential_records, next_idx = apply_gitleaks_findings(
            scannable,
            findings,
            temp_root=tmp_root,
            start_index=start_index,
        )

    for s in credential_records:
        ctx.spawn_log.append(
            {
                "type": "secret_scan",
                "tool": "gitleaks",
                "source": s.occurrences[0] if s.occurrences else "unknown",
                "placeholder": s.placeholder,
                "name": s.name,
            }
        )

    redacted.update(ignored)
    return redacted, credential_records, next_idx


def _redact_pii(
    files: dict[str, str],
    ctx: PipelineContext,
    *,
    start_index: int = 1,
) -> tuple[dict[str, str], list[SecretRecord], int]:
    """Replace PII with ``{{PII_NNN}}`` placeholders via Presidio.

    Returns ``(redacted_files, pii_records, next_index)`` so callers can chain
    the counter across multiple groups.
    """
    from pynydus.security.presidio import PIIRedactor

    redactor = PIIRedactor(start_index=start_index)
    pii_records: list[SecretRecord] = []
    redacted: dict[str, str] = {}

    for fname, content in files.items():
        result = redactor.redact(content)
        redacted[fname] = result.redacted_text
        for repl in result.replacements:
            pii_records.append(
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
            ctx.spawn_log.append(
                {
                    "type": "redaction",
                    "source": f"file:{fname}",
                    "pii_type": repl.pii_type,
                    "placeholder": repl.placeholder,
                }
            )

    return redacted, pii_records, redactor.counter


# ---------------------------------------------------------------------------
# Step 4 helpers: Spawner dispatch + parsing
# ---------------------------------------------------------------------------


def _get_spawner(agent_type: AgentType):  # noqa: ANN202
    """Return the spawner connector for the given agent type."""
    _SPAWNERS: dict[AgentType, tuple[str, str]] = {
        AgentType.OPENCLAW: ("pynydus.agents.openclaw.spawner", "OpenClawSpawner"),
        AgentType.LETTA: ("pynydus.agents.letta.spawner", "LettaSpawner"),
        AgentType.ZEROCLAW: ("pynydus.agents.zeroclaw.spawner", "ZeroClawSpawner"),
    }
    entry = _SPAWNERS.get(agent_type)
    if entry is None:
        raise ConnectorError(f"No spawner available for: {agent_type}")
    module, class_name = entry
    mod = __import__(module, fromlist=[class_name])
    return getattr(mod, class_name)()


def _parse_sources(
    source_groups: list[tuple[AgentType, Path, dict[str, str]]],
    ctx: PipelineContext,
) -> ParseResult:
    """Parse redacted files, dispatching each source group to its own spawner.

    Each group's dict is already redacted: it is passed directly to the
    spawner with bare filename keys.
    """
    combined = ParseResult()

    for src_type, _source_root, group_files in source_groups:
        spawner = _get_spawner(src_type)
        if not hasattr(spawner, "parse"):
            raise ConnectorError(f"Spawner {type(spawner).__name__} does not implement parse()")
        if not group_files:
            continue
        result: ParseResult = spawner.parse(group_files)
        combined.skills.extend(result.skills)
        combined.memory.extend(result.memory)
        combined.mcp_configs.update(result.mcp_configs)
        # Carry forward neutral metadata from last spawner that populated them
        if result.agent_name:
            combined.agent_name = result.agent_name
        if result.agent_description:
            combined.agent_description = result.agent_description
        if result.llm_model:
            combined.llm_model = result.llm_model
        if result.llm_context_window is not None:
            combined.llm_context_window = result.llm_context_window
        if result.embedding_model:
            combined.embedding_model = result.embedding_model

        ctx.spawn_log.append(
            {
                "type": "spawner_parse",
                "agent_type": src_type.value,
                "skills": [{"name": s.name, "source_file": s.source_file} for s in result.skills],
                "memory": [
                    {
                        "source_file": m.source_file,
                        "label": m.label.value if m.label else None,
                        "text_length": len(m.text),
                    }
                    for m in result.memory
                ],
            }
        )

    return combined


# ---------------------------------------------------------------------------
# Step 5 helpers: Record building
# ---------------------------------------------------------------------------


def _build_skills_module_from_parse(
    parse_result: ParseResult,
    agent_type: AgentType,
) -> SkillsModule:
    """Convert ParseResult skills into AgentSkill objects."""
    skills: list[AgentSkill] = []
    for i, rs in enumerate(parse_result.skills, start=1):
        meta: dict[str, str] = {
            "id": f"skill_{i:03d}",
            "source_framework": str(agent_type),
        }
        if rs.source_file:
            meta["source_file"] = rs.source_file
        skills.append(
            AgentSkill(
                name=rs.name,
                body=rs.content,
                metadata=meta,
            )
        )

    return SkillsModule(skills=skills)


def _build_mcp_module_from_parse(parse_result: ParseResult) -> McpModule:
    """Build McpModule from ParseResult's raw MCP config dicts."""
    return McpModule(configs=dict(parse_result.mcp_configs))


def _build_memory_module_from_parse(
    parse_result: ParseResult,
    agent_type: AgentType,
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
                agent_type=agent_type,
                source_store=rm.source_file or "unknown",
                skill_ref=rm.skill_ref,
                timestamp=rm.timestamp,
            )
        )
    return MemoryModule(memory=memory)


# ---------------------------------------------------------------------------
# Step 6 helpers: Base egg merging (FROM + SOURCE)
# ---------------------------------------------------------------------------


def _merge_skills(base: SkillsModule, extracted: SkillsModule) -> SkillsModule:
    """Combine base egg skills with freshly extracted skills, re-numbering IDs."""
    combined = list(base.skills) + list(extracted.skills)
    for i, skill in enumerate(combined, start=1):
        skill.metadata["id"] = f"skill_{i:03d}"
    return SkillsModule(skills=combined)


def _merge_mcp(base: McpModule, extracted: McpModule) -> McpModule:
    """Merge MCP server configs from base egg and parsed source."""
    merged = dict(base.configs)
    merged.update(extracted.configs)
    return McpModule(configs=merged)


def _merge_memory(base: MemoryModule, extracted: MemoryModule) -> MemoryModule:
    """Combine base egg memory with freshly extracted memory, re-numbering IDs."""
    combined = list(base.memory) + list(extracted.memory)
    for i, rec in enumerate(combined, start=1):
        rec.id = f"mem_{i:03d}"
    return MemoryModule(memory=combined)


def _merge_secrets(
    base: SecretsModule,
    extracted: SecretsModule,
) -> SecretsModule:
    """Combine base egg secrets with extracted secrets, deduplicating by name."""
    seen_names: set[str] = set()
    combined: list[SecretRecord] = []
    for s in list(base.secrets) + list(extracted.secrets):
        if s.name not in seen_names:
            combined.append(s)
            seen_names.add(s.name)
    for i, s in enumerate(combined, start=1):
        s.id = f"secret_{i:03d}"
    return SecretsModule(secrets=combined)


# ---------------------------------------------------------------------------
# Step 8 helpers: Post-processing (custom labels, memory exclusions)
# ---------------------------------------------------------------------------


def _apply_custom_labels(
    memory: MemoryModule,
    custom_labels: dict[str, str],
    spawn_log: list[dict] | None = None,
) -> None:
    """Override memory record labels based on source_store pattern matching."""
    import fnmatch

    for rec in memory.memory:
        if not rec.source_store:
            continue
        for pattern, label_str in custom_labels.items():
            if fnmatch.fnmatch(rec.source_store, pattern):
                old_label = rec.label.value
                rec.label = MemoryLabel(label_str)
                if spawn_log is not None:
                    spawn_log.append(
                        {
                            "type": "label_override",
                            "record_id": rec.id,
                            "source_store": rec.source_store,
                            "pattern": pattern,
                            "old_label": old_label,
                            "new_label": label_str,
                        }
                    )
                break


def _drop_memory_records_with_excluded_labels(
    memory: MemoryModule,
    excluded: list[MemoryLabel],
    spawn_log: list[dict] | None = None,
) -> MemoryModule:
    """Remove memory records whose label is listed in ``excluded``."""
    if not excluded:
        return memory
    excluded_set = set(excluded)
    dropped = [r for r in memory.memory if r.label in excluded_set]
    kept = [r for r in memory.memory if r.label not in excluded_set]

    if spawn_log is not None and dropped:
        spawn_log.append(
            {
                "type": "memory_excluded",
                "excluded_labels": [lbl.value for lbl in excluded],
                "dropped": [
                    {"id": r.id, "label": r.label.value, "source_store": r.source_store}
                    for r in dropped
                ],
                "kept": len(kept),
            }
        )

    return MemoryModule(memory=kept)


# ---------------------------------------------------------------------------
# Step 9 helpers: Packaging
# ---------------------------------------------------------------------------


def _package_egg(
    ctx: PipelineContext,
    skills: SkillsModule,
    mcp: McpModule,
    memory: MemoryModule,
    secrets: SecretsModule,
    parse_result: ParseResult | None = None,
) -> Egg:
    """Construct the final Egg with manifest and neutral metadata fields."""
    sources: list[SourceEntry] = [
        SourceEntry(agent_type=src.agent_type, source_path=src.path) for src in ctx.sources
    ]

    manifest = Manifest(
        nydus_version=pynydus.__version__,
        min_nydus_version="0.0.7",
        egg_version=pynydus.EGG_SPEC_VERSION,
        created_at=datetime.now(UTC),
        agent_type=ctx.agent_type,
        redaction_policy=RedactionPolicy(
            pii_redacted=ctx.redact,
            secrets_placeholder_only=ctx.redact,
        ),
        base_egg=ctx.base_egg,
        source_dir=str(ctx.nydusfile_dir),
        sources=sources,
    )

    if parse_result:
        manifest.agent_name = parse_result.agent_name
        manifest.agent_description = parse_result.agent_description
        manifest.llm_model = parse_result.llm_model
        manifest.llm_context_window = parse_result.llm_context_window
        manifest.embedding_model = parse_result.embedding_model

    egg = Egg(
        manifest=manifest,
        skills=skills,
        mcp=mcp,
        memory=memory,
        secrets=secrets,
    )

    ctx.spawn_log.append(
        {
            "type": "egg_packaged",
            "agent_type": ctx.agent_type.value if ctx.agent_type else None,
            "skills": len(skills.skills),
            "memory": len(memory.memory),
            "secrets": len(secrets.secrets),
        }
    )

    return egg


# ---------------------------------------------------------------------------
# Step 10 helpers: Standards artifact generation
# ---------------------------------------------------------------------------


def _stash_apm(
    groups: list[tuple[AgentType, Path, dict[str, str]]],
    ctx: PipelineContext,
) -> str | None:
    """Find and return apm.yml content from source files (passthrough)."""
    for _src_type, source_root, group_files in groups:
        if "apm.yml" in group_files:
            ctx.spawn_log.append({"type": "apm_passthrough", "source": "apm.yml"})
            return group_files["apm.yml"]
        apm_path = source_root / "apm.yml"
        if apm_path.is_file():
            ctx.spawn_log.append({"type": "apm_passthrough", "source": str(apm_path)})
            return apm_path.read_text(encoding="utf-8")
    return None


def _resolve_a2a_card(
    groups: list[tuple[AgentType, Path, dict[str, str]]],
    egg: Egg,
    ctx: PipelineContext,
) -> dict | None:
    """Return A2A card: passthrough from source or generate from egg."""
    import json

    from pynydus.standards import a2a

    for _src_type, source_root, group_files in groups:
        if "agent-card.json" in group_files:
            try:
                ctx.spawn_log.append({"type": "a2a_passthrough", "source": "agent-card.json"})
                return json.loads(group_files["agent-card.json"])
            except json.JSONDecodeError:
                logger.warning("Failed to parse agent-card.json from source, will generate")
            break
        card_path = source_root / "agent-card.json"
        if card_path.is_file():
            try:
                ctx.spawn_log.append({"type": "a2a_passthrough", "source": str(card_path)})
                return json.loads(card_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Failed to parse agent-card.json from source, will generate")
            break

    if egg.a2a_card is not None:
        return None

    card_files = a2a.generate(egg)
    if "agent-card.json" in card_files:
        ctx.spawn_log.append({"type": "a2a_generated"})
        return json.loads(card_files["agent-card.json"])
    return None


def _embed_spec_snapshots(ctx: PipelineContext) -> dict[str, str] | None:
    """Load spec markdown files and build the snapshots dict with manifest.json."""
    import json
    import re

    from pynydus.standards import load_spec

    spec_snapshots: dict[str, str] = {}
    spec_versions: dict[str, dict[str, str]] = {}
    for spec_name in ("mcp", "agentskills", "a2a", "apm", "agents"):
        try:
            md_text, _schema = load_spec(spec_name)
            spec_snapshots[f"{spec_name}.md"] = md_text
            version_match = re.search(r"Spec version:\s*(.+)", md_text)
            source_match = re.search(r"Source:\s*(.+)", md_text)
            spec_versions[spec_name] = {
                "version": version_match.group(1).strip() if version_match else "unknown",
                "source": source_match.group(1).strip() if source_match else "unknown",
            }
        except FileNotFoundError:
            logger.warning("Spec file not found: %s.md", spec_name)

    if not spec_snapshots:
        return None

    spec_snapshots["manifest.json"] = json.dumps(
        {"nydus_version": pynydus.__version__, "specs": spec_versions},
        indent=2,
    )
    ctx.spawn_log.append({"type": "specs_embedded", "specs": list(spec_snapshots.keys())})
    return spec_snapshots


def _generate_standards_artifacts(
    egg: Egg,
    groups: list[tuple[AgentType, Path, dict[str, str]]],
    ctx: PipelineContext,
) -> Egg:
    """Generate A2A card, AGENTS.md, spec snapshots, and stash apm.yml.

    Mutates nothing. Returns a new Egg via ``model_copy()``.
    """
    from pynydus.standards import agents_md

    updates: dict = {}

    apm = _stash_apm(groups, ctx)
    if apm is not None:
        updates["apm_yml"] = apm

    card = _resolve_a2a_card(groups, egg.model_copy(update=updates), ctx)
    if card is not None:
        updates["a2a_card"] = card

    temp_egg = egg.model_copy(update=updates)
    if temp_egg.agents_md is None:
        md_files = agents_md.generate(temp_egg)
        if "AGENTS.md" in md_files:
            updates["agents_md"] = md_files["AGENTS.md"]
            ctx.spawn_log.append({"type": "agents_md_generated"})

    snapshots = _embed_spec_snapshots(ctx)
    if snapshots is not None:
        updates["spec_snapshots"] = snapshots

    return egg.model_copy(update=updates)
