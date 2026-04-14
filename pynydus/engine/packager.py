"""Egg packaging and reading: archive operations for .egg files.

An .egg file is a zip archive with the canonical directory layout::

    manifest.json
    signature.json           (optional: Ed25519 signature over modules)
    spawn_log.json           (structured spawn pipeline log)
    nydus.json               (per-skill ID/agent_type mapping)
    mcp.json                 (MCP server configs, Claude Desktop format)
    agent-card.json          (A2A agent card, optional)
    apm.yml                  (passthrough from source, optional)
    AGENTS.md                (per-egg deployment runbook, optional)
    skills/<slug>/SKILL.md   (Agent Skills format: agentskills.io)
    specs/...                (embedded spec snapshots, optional)
    memory.json
    secrets.json
    raw/...
    Nydusfile                (spawn DSL)
"""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pynydus.api.errors import EggError
from pynydus.api.schemas import (
    Egg,
    Manifest,
    McpModule,
    MemoryModule,
    SecretsModule,
    SkillsModule,
)
from pynydus.api.skill_format import (
    AgentSkill,
    parse_skill_md,
    render_skill_md,
    skill_slug,
)

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Archive layout constants: single source of truth for .egg ZIP entry names
# ---------------------------------------------------------------------------
MANIFEST_ENTRY = "manifest.json"
MEMORY_ENTRY = "memory.json"
SECRETS_ENTRY = "secrets.json"
SIGNATURE_ENTRY = "signature.json"
NYDUS_META_ENTRY = "nydus.json"
SPAWN_LOG_ENTRY = "spawn_log.json"
MCP_ENTRY = "mcp.json"
AGENT_CARD_ENTRY = "agent-card.json"
APM_ENTRY = "apm.yml"
AGENTS_MD_ENTRY = "AGENTS.md"
EMBEDDED_NYDUSFILE_NAME = "Nydusfile"
SKILLS_PREFIX = "skills/"
SPECS_PREFIX = "specs/"
RAW_PREFIX = "raw/"

# Legacy layout (read-only backward compat)
_LEGACY_MCP_PREFIX = "mcp/"


def _sign_if_key(
    private_key: Ed25519PrivateKey | None,
    content_parts: list[bytes],
) -> dict | None:
    """Return signature data dict if a private key is provided."""
    if private_key is None:
        return None

    from pynydus.security.signing import sign_egg_content

    return sign_egg_content(private_key, content_parts)


# ---------------------------------------------------------------------------
# Skills serialization helpers
# ---------------------------------------------------------------------------


def _write_skills_to_zip(zf: zipfile.ZipFile, skills: SkillsModule) -> bytes:
    """Write each skill as ``skills/<slug>/SKILL.md``.

    Also writes ``nydus.json`` (per-skill tracking metadata sidecar).

    Returns the concatenated bytes of all SKILL.md files (sorted by slug)
    for deterministic signing.
    """
    parts: list[tuple[str, bytes]] = []
    seen_slugs: set[str] = set()
    nydus_meta: dict[str, dict[str, str]] = {}

    for skill in skills.skills:
        md_text = render_skill_md(skill)
        slug = skill_slug(skill.name)

        base_slug = slug
        counter = 2
        while slug in seen_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1
        seen_slugs.add(slug)

        md_bytes = md_text.encode("utf-8")
        zf.writestr(f"{SKILLS_PREFIX}{slug}/SKILL.md", md_bytes)

        nydus_meta[slug] = {
            "id": skill.metadata.get("id", slug),
            "agent_type": skill.metadata.get("source_framework", "unknown"),
        }
        parts.append((slug, md_bytes))

    if nydus_meta:
        zf.writestr(NYDUS_META_ENTRY, json.dumps(nydus_meta, indent=2))

    parts.sort(key=lambda t: t[0])
    return b"".join(b for _, b in parts)


def _write_mcp_to_zip(zf: zipfile.ZipFile, mcp: McpModule) -> None:
    """Write MCP configs as a single ``mcp.json`` in Claude Desktop format."""
    if not mcp.configs:
        return
    doc = {"mcpServers": mcp.configs}
    zf.writestr(MCP_ENTRY, json.dumps(doc, indent=2))


def _read_skills_from_zip(zf: zipfile.ZipFile) -> SkillsModule:
    """Read skills from ``skills/<slug>/SKILL.md`` + ``nydus.json``."""
    names = zf.namelist()

    skill_mds: dict[str, str] = {}
    for name in names:
        if name.startswith(SKILLS_PREFIX) and name.endswith("/SKILL.md"):
            parts = name.split("/")
            if len(parts) == 3:
                skill_mds[parts[1]] = zf.read(name).decode("utf-8")

    nydus_meta: dict[str, dict] = {}
    if NYDUS_META_ENTRY in names:
        try:
            nydus_meta = json.loads(zf.read(NYDUS_META_ENTRY))
        except json.JSONDecodeError:
            logger.warning("Failed to parse %s", NYDUS_META_ENTRY)

    if skill_mds:
        skills: list[AgentSkill] = []
        for slug in sorted(skill_mds):
            agent_skill = parse_skill_md(skill_mds[slug])
            meta = nydus_meta.get(slug, {})
            skill_id = meta.get("id", slug)
            agent_type = meta.get(
                "agent_type", agent_skill.metadata.get("source_framework", "unknown")
            )
            agent_skill.metadata.setdefault("id", skill_id)
            agent_skill.metadata.setdefault("source_framework", agent_type)
            skills.append(agent_skill)
        return SkillsModule(skills=skills)

    return SkillsModule()


def _read_mcp_from_zip(zf: zipfile.ZipFile) -> McpModule:
    """Read MCP configs from ``mcp.json`` (Claude Desktop format).

    Falls back to legacy ``mcp/<name>.json`` per-server files for old eggs.
    """
    names = zf.namelist()

    if MCP_ENTRY in names:
        try:
            data = json.loads(zf.read(MCP_ENTRY))
            servers = data.get("mcpServers", data)
            if isinstance(servers, dict):
                return McpModule(configs=servers)
        except json.JSONDecodeError:
            logger.warning("Failed to parse %s", MCP_ENTRY)

    # Legacy: mcp/<name>.json per-server files
    configs: dict[str, dict[str, Any]] = {}
    for name in names:
        if name.startswith(_LEGACY_MCP_PREFIX) and name.endswith(".json"):
            server_name = Path(name).stem
            if server_name in configs:
                continue
            try:
                configs[server_name] = json.loads(zf.read(name))
            except json.JSONDecodeError:
                logger.warning("Failed to parse MCP config: %s", name)

    return McpModule(configs=configs)


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------


def _write_egg_archive(
    egg: Egg,
    output_path: Path,
    raw_artifacts: dict[str, str] | None = None,
    spawn_log: list[dict] | None = None,
    *,
    nydusfile_text: str | None = None,
    private_key: Ed25519PrivateKey | None = None,
) -> Path:
    """Write an Egg to a .egg archive (zip-based)."""
    output_path = output_path.with_suffix(".egg")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    old_sig = egg.manifest.signature
    egg.manifest.signature = ""
    manifest_bytes = egg.manifest.model_dump_json(indent=2).encode()
    memory_bytes = egg.memory.model_dump_json(indent=2).encode()
    secrets_bytes = egg.secrets.model_dump_json(indent=2).encode()

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        skills_bytes = _write_skills_to_zip(zf, egg.skills)
        _write_mcp_to_zip(zf, egg.mcp)

        zf.writestr(MEMORY_ENTRY, memory_bytes)
        zf.writestr(SECRETS_ENTRY, secrets_bytes)

        if raw_artifacts:
            for name, content in raw_artifacts.items():
                zf.writestr(f"{RAW_PREFIX}{name}", content)

        if nydusfile_text:
            zf.writestr(EMBEDDED_NYDUSFILE_NAME, nydusfile_text)

        zf.writestr(
            SPAWN_LOG_ENTRY,
            json.dumps(spawn_log or [], indent=2),
        )

        if egg.apm_yml:
            zf.writestr(APM_ENTRY, egg.apm_yml)

        if egg.a2a_card:
            zf.writestr(AGENT_CARD_ENTRY, json.dumps(egg.a2a_card, indent=2))

        if egg.agents_md:
            zf.writestr(AGENTS_MD_ENTRY, egg.agents_md)

        if egg.spec_snapshots:
            for spec_name, spec_content in egg.spec_snapshots.items():
                zf.writestr(f"{SPECS_PREFIX}{spec_name}", spec_content)

        sig_data = _sign_if_key(
            private_key,
            [manifest_bytes, skills_bytes, memory_bytes, secrets_bytes],
        )
        if sig_data:
            egg.manifest.signature = sig_data["signature"]
            zf.writestr(SIGNATURE_ENTRY, json.dumps(sig_data, indent=2))
        else:
            egg.manifest.signature = old_sig
        zf.writestr(MANIFEST_ENTRY, egg.manifest.model_dump_json(indent=2))

    return output_path


def save(
    egg: Egg,
    output_path: Path,
    *,
    raw_artifacts: dict[str, str] | None = None,
    spawn_log: list[dict] | None = None,
    nydusfile_text: str | None = None,
    private_key: Ed25519PrivateKey | None = None,
) -> Path:
    """Write an Egg to a ``.egg`` file, including ``raw/`` and ``spawn_log.json``.

    Uses ``egg.raw_artifacts``, ``egg.spawn_log``, and ``egg.nydusfile`` when
    the corresponding keyword arguments are omitted.

    Args:
        egg: Egg to serialize.
        output_path: Destination path (``.egg`` suffix applied if missing).
        raw_artifacts: Redacted ``raw/`` snapshot. defaults to ``egg.raw_artifacts``.
        spawn_log: Pipeline log. defaults to ``egg.spawn_log``.
        nydusfile_text: Embedded DSL text. defaults to ``egg.nydusfile``.
        private_key: If set, signs manifest + module payloads (Ed25519).

    Returns:
        Path to the written ``.egg`` archive.
    """
    ra = egg.raw_artifacts if raw_artifacts is None else raw_artifacts
    sl = egg.spawn_log if spawn_log is None else spawn_log
    nf = egg.nydusfile if nydusfile_text is None else nydusfile_text
    return _write_egg_archive(
        egg,
        output_path,
        ra,
        sl,
        nydusfile_text=nf,
        private_key=private_key,
    )


def _unpack_egg_core(egg_path: Path) -> Egg:
    """Load manifest, skills, MCP, memory, and secrets from an archive."""
    if not egg_path.exists():
        raise EggError(f"Egg file not found: {egg_path}")

    try:
        with zipfile.ZipFile(egg_path, "r") as zf:
            names = zf.namelist()
            manifest_data = json.loads(zf.read(MANIFEST_ENTRY))
            skills_module = _read_skills_from_zip(zf)
            mcp_module = _read_mcp_from_zip(zf)
            memory_data = json.loads(zf.read(MEMORY_ENTRY))
            secrets_data = json.loads(zf.read(SECRETS_ENTRY))

            a2a_card = None
            if AGENT_CARD_ENTRY in names:
                try:
                    a2a_card = json.loads(zf.read(AGENT_CARD_ENTRY))
                except json.JSONDecodeError:
                    logger.warning("Failed to parse %s", AGENT_CARD_ENTRY)

            agents_md = None
            if AGENTS_MD_ENTRY in names:
                agents_md = zf.read(AGENTS_MD_ENTRY).decode("utf-8")

            apm_yml = None
            if APM_ENTRY in names:
                apm_yml = zf.read(APM_ENTRY).decode("utf-8")

            spec_snapshots: dict[str, str] | None = None
            spec_entries = [n for n in names if n.startswith(SPECS_PREFIX) and not n.endswith("/")]
            if spec_entries:
                spec_snapshots = {}
                for entry in spec_entries:
                    key = entry[len(SPECS_PREFIX) :]
                    spec_snapshots[key] = zf.read(entry).decode("utf-8")

    except (KeyError, zipfile.BadZipFile) as e:
        raise EggError(f"Invalid Egg archive: {e}") from e

    # Strip fields that don't exist in the current Manifest model
    manifest_data.pop("included_modules", None)
    manifest_data.pop("source_metadata", None)

    return Egg(
        manifest=Manifest(**manifest_data),
        skills=skills_module,
        mcp=mcp_module,
        memory=MemoryModule(**memory_data),
        secrets=SecretsModule(**secrets_data),
        a2a_card=a2a_card,
        agents_md=agents_md,
        apm_yml=apm_yml,
        spec_snapshots=spec_snapshots,
    )


def read_spawn_log_list(egg_path: Path) -> list[dict]:
    """Return the spawn pipeline log as a list (same as ``spawn_log.json`` body).

    Args:
        egg_path: Path to the ``.egg`` archive.

    Returns:
        Log entries, or an empty list if the entry is missing or not a list.
    """
    blob = read_logs(egg_path).get(SPAWN_LOG_ENTRY)
    if blob is None:
        return []
    if isinstance(blob, list):
        return blob
    return []


def load(egg_path: Path, *, include_raw: bool = True) -> Egg:
    """Load a fully populated :class:`~pynydus.api.schemas.Egg` from a ``.egg`` archive.

    Includes ``spawn_log.json`` as ``spawn_log`` and embedded ``Nydusfile`` text when
    present. When ``include_raw`` is ``True`` (default), ``raw/`` entries are read into
    ``raw_artifacts``. Set ``include_raw=False`` to skip loading ``raw/`` (empty dict) and
    reduce memory use for large archives. use :func:`read_raw_artifacts` when you need
    ``raw/`` for passthrough hatch or inspection.

    Args:
        egg_path: Path to the ``.egg`` archive.
        include_raw: When ``False``, skip reading ``raw/`` into memory.

    Returns:
        Egg with modules, optional ``raw_artifacts``, ``spawn_log``, and ``nydusfile``.
    """
    egg = _unpack_egg_core(egg_path)
    raw = read_raw_artifacts(egg_path) if include_raw else {}
    sl = read_spawn_log_list(egg_path)
    nf = read_nydusfile(egg_path)
    return egg.model_copy(update={"raw_artifacts": raw, "spawn_log": sl, "nydusfile": nf})


def read_raw_artifacts(egg_path: Path) -> dict[str, str]:
    """Read ``raw/`` artifacts from an Egg archive.

    Args:
        egg_path: Path to the ``.egg`` archive.

    Returns:
        Mapping of relative path (under ``raw/``) to UTF-8 text content.
    """
    artifacts: dict[str, str] = {}
    with zipfile.ZipFile(egg_path, "r") as zf:
        for name in zf.namelist():
            if name.startswith(RAW_PREFIX) and not name.endswith("/"):
                key = name[len(RAW_PREFIX) :]
                artifacts[key] = zf.read(name).decode("utf-8")
    return artifacts


def read_logs(egg_path: Path) -> dict[str, list]:
    """Read structured logs from an Egg archive.

    Args:
        egg_path: Path to the ``.egg`` archive.

    Returns:
        Dict keyed by ZIP entry name (e.g. ``spawn_log.json``) to parsed JSON lists.
    """
    logs: dict[str, list] = {}
    with zipfile.ZipFile(egg_path, "r") as zf:
        if SPAWN_LOG_ENTRY in zf.namelist():
            logs[SPAWN_LOG_ENTRY] = json.loads(zf.read(SPAWN_LOG_ENTRY))
    return logs


def read_nydusfile(egg_path: Path) -> str | None:
    """Read the embedded Nydusfile text from an Egg archive, or None if absent.

    Args:
        egg_path: Path to the ``.egg`` archive.

    Returns:
        Embedded Nydusfile source, or ``None`` if not stored in the archive.
    """
    with zipfile.ZipFile(egg_path, "r") as zf:
        if EMBEDDED_NYDUSFILE_NAME in zf.namelist():
            return zf.read(EMBEDDED_NYDUSFILE_NAME).decode("utf-8")
        return None


def read_signature(egg_path: Path) -> dict | None:
    """Read ``signature.json`` from an Egg archive, or None if unsigned.

    Args:
        egg_path: Path to the ``.egg`` archive.

    Returns:
        Parsed signature payload, or ``None`` when the archive is unsigned.
    """
    with zipfile.ZipFile(egg_path, "r") as zf:
        if SIGNATURE_ENTRY not in zf.namelist():
            return None
        return json.loads(zf.read(SIGNATURE_ENTRY))


def _read_skills_bytes_for_verification(zf: zipfile.ZipFile) -> bytes:
    """Reconstruct the skills bytes used for signing."""
    skill_parts: list[tuple[str, bytes]] = []
    for name in zf.namelist():
        if name.startswith(SKILLS_PREFIX) and name.endswith("/SKILL.md"):
            parts = name.split("/")
            if len(parts) == 3:
                skill_parts.append((parts[1], zf.read(name)))

    if skill_parts:
        skill_parts.sort(key=lambda t: t[0])
        return b"".join(b for _, b in skill_parts)

    return b""


def verify_egg_archive(egg_path: Path) -> bool | None:
    """Verify an egg archive's signature.

    Args:
        egg_path: Path to the ``.egg`` archive.

    Returns:
        ``True`` if a signature is present and valid. ``False`` if present but
        invalid (tampered). ``None`` if the egg is unsigned.
    """
    sig_data = read_signature(egg_path)
    if sig_data is None:
        return None

    from pynydus.security.signing import verify_egg_content

    with zipfile.ZipFile(egg_path, "r") as zf:
        try:
            manifest_data = json.loads(zf.read(MANIFEST_ENTRY))
            manifest_data.pop("included_modules", None)
            manifest_data.pop("source_metadata", None)
            manifest = Manifest(**manifest_data)
            manifest.signature = ""
            manifest_bytes = manifest.model_dump_json(indent=2).encode()
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Cannot verify egg signature: %s", exc)
            return False

        content_parts = [
            manifest_bytes,
            _read_skills_bytes_for_verification(zf),
            zf.read(MEMORY_ENTRY),
            zf.read(SECRETS_ENTRY),
        ]

    return verify_egg_content(sig_data, content_parts)
