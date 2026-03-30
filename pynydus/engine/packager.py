"""Egg packaging and reading — archive operations for .egg files. Spec §4.

An .egg file is a zip archive with the canonical directory layout::

    manifest.json
    signature.json           (optional — Ed25519 signature over modules)
    spawn_log.json           (structured spawn pipeline log)
    nydus.json               (per-skill ID/source_type mapping)
    apm.yml                  (APM compatibility manifest)
    skills/<slug>/SKILL.md   (Agent Skills format — agentskills.io)
    mcp/<server>.json        (MCP server configs — modelcontextprotocol.io)
    memory.json
    secrets.json
    raw/...
    attachments/...
    Nydusfile                (optional — copy of spawn DSL)
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
    McpServerConfig,
    MemoryModule,
    SecretsModule,
    SkillRecord,
    SkillsModule,
)
from pynydus.api.skill_format import (
    agent_skill_to_skill_record,
    parse_skill_md,
    render_skill_md,
    skill_record_to_agent_skill,
    skill_slug,
)

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Archive layout constants — single source of truth for .egg ZIP entry names
# ---------------------------------------------------------------------------
MANIFEST_ENTRY = "manifest.json"
MEMORY_ENTRY = "memory.json"
SECRETS_ENTRY = "secrets.json"
SIGNATURE_ENTRY = "signature.json"
NYDUS_META_ENTRY = "nydus.json"
SPAWN_LOG_ENTRY = "spawn_log.json"
APM_ENTRY = "apm.yml"
EMBEDDED_NYDUSFILE_NAME = "Nydusfile"
SKILLS_PREFIX = "skills/"
MCP_PREFIX = "mcp/"
RAW_PREFIX = "raw/"


def _sign_if_key(
    private_key: Ed25519PrivateKey | None,
    content_parts: list[bytes],
) -> dict | None:
    """Return signature data dict if a private key is provided."""
    if private_key is None:
        return None

    from pynydus.pkg.signing import sign_egg_content

    return sign_egg_content(private_key, content_parts)


# ---------------------------------------------------------------------------
# Skills serialization helpers
# ---------------------------------------------------------------------------


def _write_skills_to_zip(zf: zipfile.ZipFile, skills: SkillsModule) -> bytes:
    """Write each skill as ``skills/<slug>/SKILL.md``.

    Also writes ``nydus.json`` (per-skill ID/source_type mapping) and
    MCP server configs to ``mcp/<server>.json``.

    Returns the concatenated bytes of all SKILL.md files (sorted by slug)
    for deterministic signing.
    """
    parts: list[tuple[str, bytes]] = []
    seen_slugs: set[str] = set()
    nydus_meta: dict[str, dict[str, str]] = {}

    for skill in skills.skills:
        agent_skill = skill_record_to_agent_skill(skill)
        md_text = render_skill_md(agent_skill)
        slug = skill_slug(skill.name)

        base_slug = slug
        counter = 2
        while slug in seen_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1
        seen_slugs.add(slug)

        md_bytes = md_text.encode("utf-8")
        zf.writestr(f"{SKILLS_PREFIX}{slug}/SKILL.md", md_bytes)

        nydus_meta[slug] = {"id": skill.id, "source_type": skill.source_type}
        parts.append((slug, md_bytes))

    if nydus_meta:
        zf.writestr(NYDUS_META_ENTRY, json.dumps(nydus_meta, indent=2))

    for name in sorted(skills.mcp_configs):
        cfg = skills.mcp_configs[name]
        cfg_bytes = json.dumps(cfg.model_dump(exclude_defaults=True), indent=2).encode()
        zf.writestr(f"{MCP_PREFIX}{name}.json", cfg_bytes)

    parts.sort(key=lambda t: t[0])
    return b"".join(b for _, b in parts)


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
        except (json.JSONDecodeError, Exception):
            logger.warning("Failed to parse %s", NYDUS_META_ENTRY)

    mcp_configs: dict[str, McpServerConfig] = {}
    for name in names:
        if name.startswith(MCP_PREFIX) and name.endswith(".json"):
            server_name = Path(name).stem
            if server_name in mcp_configs:
                continue
            try:
                cfg_data = json.loads(zf.read(name))
                mcp_configs[server_name] = McpServerConfig(**cfg_data)
            except (json.JSONDecodeError, Exception):
                logger.warning("Failed to parse MCP config: %s", name)

    if skill_mds:
        skills: list[SkillRecord] = []
        for i, slug in enumerate(sorted(skill_mds), start=1):
            agent_skill = parse_skill_md(skill_mds[slug])
            meta = nydus_meta.get(slug, {})
            skill_id = meta.get("id", f"skill_{i:03d}")
            source_type = meta.get("source_type", agent_skill.metadata.get("source_framework", "unknown"))
            record_dict = agent_skill_to_skill_record(
                agent_skill, skill_id=skill_id, source_type=source_type,
            )
            skills.append(SkillRecord(**record_dict))
        return SkillsModule(skills=skills, mcp_configs=mcp_configs)

    return SkillsModule(mcp_configs=mcp_configs)


# ---------------------------------------------------------------------------
# Pack / unpack
# ---------------------------------------------------------------------------


def _build_apm_yml(egg: Egg) -> str:
    """Generate an ``apm.yml`` manifest for APM compatibility."""
    import yaml as _yaml

    skills_list = []
    for s in egg.skills.skills:
        entry: dict[str, Any] = {"name": skill_slug(s.name)}
        if s.metadata.get("description"):
            entry["description"] = s.metadata["description"]
        skills_list.append(entry)

    mcp_list = []
    for name in sorted(egg.skills.mcp_configs):
        cfg = egg.skills.mcp_configs[name]
        entry = {"name": name}
        if cfg.command:
            entry["command"] = cfg.command
        if cfg.url:
            entry["url"] = cfg.url
        mcp_list.append(entry)

    doc: dict[str, Any] = {
        "name": egg.manifest.source_metadata.get("namespace", "nydus/agent"),
        "version": egg.manifest.egg_version,
        "source_type": egg.manifest.source_type.value,
    }
    if skills_list:
        doc["skills"] = skills_list
    if mcp_list:
        doc["mcp_servers"] = mcp_list

    return _yaml.dump(doc, default_flow_style=False, sort_keys=False)


def pack(
    egg: Egg,
    output_path: Path,
    *,
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

        zf.writestr(MEMORY_ENTRY, memory_bytes)
        zf.writestr(SECRETS_ENTRY, secrets_bytes)

        if egg.raw_dir and egg.raw_dir.is_dir():
            for fpath in egg.raw_dir.rglob("*"):
                if fpath.is_file():
                    arcname = f"{RAW_PREFIX}{fpath.relative_to(egg.raw_dir)}"
                    zf.write(fpath, arcname)

        zf.writestr(SPAWN_LOG_ENTRY, "[]")
        zf.writestr(APM_ENTRY, _build_apm_yml(egg))

        sig_data = _sign_if_key(
            private_key,
            [manifest_bytes, skills_bytes, memory_bytes, secrets_bytes],
        )
        if sig_data:
            egg.manifest.signature = sig_data["signature"]
            zf.writestr(MANIFEST_ENTRY, egg.manifest.model_dump_json(indent=2))
            zf.writestr(SIGNATURE_ENTRY, json.dumps(sig_data, indent=2))
        else:
            egg.manifest.signature = old_sig
            zf.writestr(MANIFEST_ENTRY, egg.manifest.model_dump_json(indent=2))

    return output_path


def pack_with_raw(
    egg: Egg,
    output_path: Path,
    raw_artifacts: dict[str, str],
    spawn_log: list[dict] | None = None,
    *,
    nydusfile_text: str | None = None,
    private_key: Ed25519PrivateKey | None = None,
) -> Path:
    """Pack an Egg with raw artifacts provided as a dict."""
    output_path = output_path.with_suffix(".egg")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    old_sig = egg.manifest.signature
    egg.manifest.signature = ""
    manifest_bytes = egg.manifest.model_dump_json(indent=2).encode()
    memory_bytes = egg.memory.model_dump_json(indent=2).encode()
    secrets_bytes = egg.secrets.model_dump_json(indent=2).encode()

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        skills_bytes = _write_skills_to_zip(zf, egg.skills)

        zf.writestr(MEMORY_ENTRY, memory_bytes)
        zf.writestr(SECRETS_ENTRY, secrets_bytes)

        for name, content in raw_artifacts.items():
            zf.writestr(f"{RAW_PREFIX}{name}", content)

        if nydusfile_text:
            zf.writestr(EMBEDDED_NYDUSFILE_NAME, nydusfile_text)

        zf.writestr(
            SPAWN_LOG_ENTRY,
            json.dumps(spawn_log or [], indent=2),
        )
        zf.writestr(APM_ENTRY, _build_apm_yml(egg))

        sig_data = _sign_if_key(
            private_key,
            [manifest_bytes, skills_bytes, memory_bytes, secrets_bytes],
        )
        if sig_data:
            egg.manifest.signature = sig_data["signature"]
            zf.writestr(MANIFEST_ENTRY, egg.manifest.model_dump_json(indent=2))
            zf.writestr(SIGNATURE_ENTRY, json.dumps(sig_data, indent=2))
        else:
            egg.manifest.signature = old_sig
            zf.writestr(MANIFEST_ENTRY, egg.manifest.model_dump_json(indent=2))

    return output_path


def unpack(egg_path: Path) -> Egg:
    """Read a .egg archive and return an Egg object."""
    if not egg_path.exists():
        raise EggError(f"Egg file not found: {egg_path}")

    try:
        with zipfile.ZipFile(egg_path, "r") as zf:
            manifest_data = json.loads(zf.read(MANIFEST_ENTRY))
            skills_module = _read_skills_from_zip(zf)
            memory_data = json.loads(zf.read(MEMORY_ENTRY))
            secrets_data = json.loads(zf.read(SECRETS_ENTRY))
    except (KeyError, zipfile.BadZipFile) as e:
        raise EggError(f"Invalid Egg archive: {e}") from e

    return Egg(
        manifest=Manifest(**manifest_data),
        skills=skills_module,
        memory=MemoryModule(**memory_data),
        secrets=SecretsModule(**secrets_data),
    )


def read_raw_artifacts(egg_path: Path) -> dict[str, str]:
    """Read raw/ artifacts from an Egg archive."""
    artifacts: dict[str, str] = {}
    with zipfile.ZipFile(egg_path, "r") as zf:
        for name in zf.namelist():
            if name.startswith(RAW_PREFIX) and not name.endswith("/"):
                key = name[len(RAW_PREFIX):]
                artifacts[key] = zf.read(name).decode("utf-8")
    return artifacts


def read_logs(egg_path: Path) -> dict[str, list]:
    """Read structured logs from an Egg archive."""
    logs: dict[str, list] = {}
    with zipfile.ZipFile(egg_path, "r") as zf:
        if SPAWN_LOG_ENTRY in zf.namelist():
            logs[SPAWN_LOG_ENTRY] = json.loads(zf.read(SPAWN_LOG_ENTRY))
    return logs


def read_nydusfile(egg_path: Path) -> str | None:
    """Read the embedded Nydusfile text from an Egg archive, or None if absent."""
    with zipfile.ZipFile(egg_path, "r") as zf:
        if EMBEDDED_NYDUSFILE_NAME in zf.namelist():
            return zf.read(EMBEDDED_NYDUSFILE_NAME).decode("utf-8")
        return None


def read_signature(egg_path: Path) -> dict | None:
    """Read signature.json from an Egg archive, or None if unsigned."""
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

    Returns:
        True  — signature present and valid
        False — signature present but INVALID (tampered)
        None  — no signature (unsigned egg)
    """
    sig_data = read_signature(egg_path)
    if sig_data is None:
        return None

    from pynydus.pkg.signing import verify_egg_content

    with zipfile.ZipFile(egg_path, "r") as zf:
        try:
            manifest = Manifest(**json.loads(zf.read(MANIFEST_ENTRY)))
            manifest.signature = ""
            manifest_bytes = manifest.model_dump_json(indent=2).encode()
        except Exception:
            return False

        content_parts = [
            manifest_bytes,
            _read_skills_bytes_for_verification(zf),
            zf.read(MEMORY_ENTRY),
            zf.read(SECRETS_ENTRY),
        ]

    return verify_egg_content(sig_data, content_parts)
