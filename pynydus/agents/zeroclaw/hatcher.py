"""ZeroClaw hatcher connector. Spec §11.6.

Produces a valid ZeroClaw project directory from an Egg:
- persona.md           <- persona memory (minus identity records)
- identity.md          <- persona memory originating from IDENTITY.md / identity.json
- agents.md            <- flow memory
- user.md              <- context memory (minus tools records)
- tools.md             <- context memory originating from TOOLS.md
- knowledge.md         <- undated state memory
- memory/YYYY-MM-DD.md <- dated state memory (one file per day)
- tools/               <- skill records as Python tool files
- config.toml          <- credential placeholders + round-tripped source metadata
- .zeroclaw/           <- marker directory for project detection
- mcp/                 <- MCP server configs

All 4 MemoryLabel values have explicit file mappings.  Records are
fanned back to separate files using ``source_store`` metadata, matching
the structure the spawner reads on ingest.
"""

from __future__ import annotations

import re
from collections import defaultdict

from pynydus.api.errors import HatchError
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import (
    Egg,
    MemoryRecord,
)
from pynydus.common.connector_utils import skill_to_filename as _skill_to_filename
from pynydus.common.enums import MemoryLabel, SecretKind


def _is_identity_source(rec: MemoryRecord) -> bool:
    """True if this persona record originated from IDENTITY.md or identity.json."""
    return rec.source_store.lower() in ("identity.md", "identity.json")


def _is_tools_source(rec: MemoryRecord) -> bool:
    """True if this context record originated from TOOLS.md."""
    return rec.source_store.lower() in ("tools.md",)


def _date_key_from_record(rec: MemoryRecord) -> str | None:
    """Extract a YYYY-MM-DD date key from a state record.

    Prefers the record's timestamp field; falls back to extracting a date
    from source_store (e.g. ``memory/2026-04-01.md``).
    """
    if rec.timestamp:
        return rec.timestamp.strftime("%Y-%m-%d")
    m = re.search(r"(\d{4}-\d{2}-\d{2})", rec.source_store)
    if m:
        return m.group(1)
    return None


def _join_records(records: list[MemoryRecord]) -> str:
    """Join memory records into a single file's content."""
    return "\n\n".join(r.text for r in records) + "\n"


def _build_config_toml(
    credentials: list[tuple[str, str]],
    source_metadata: dict[str, str],
) -> str:
    """Build a TOML config string from credentials and source metadata."""
    lines: list[str] = []

    agent_name = source_metadata.get("zeroclaw.agent.name") or source_metadata.get(
        "zeroclaw.name"
    )
    agent_model = source_metadata.get("zeroclaw.agent.model") or source_metadata.get(
        "zeroclaw.model"
    )
    agent_version = source_metadata.get("zeroclaw.version")

    if agent_name or agent_model or agent_version:
        lines.append("[agent]")
        if agent_name:
            lines.append(f'name = "{agent_name}"')
        if agent_model:
            lines.append(f'model = "{agent_model}"')
        if agent_version:
            lines.append(f'version = "{agent_version}"')
        lines.append("")

    if credentials:
        lines.append("[credentials]")
        for name, placeholder in credentials:
            lines.append(f'{name} = "{placeholder}"')
        lines.append("")

    return "\n".join(lines) + "\n" if lines else ""


class ZeroClawHatcher:
    """Produce a valid ZeroClaw project directory from an Egg."""

    def render(self, egg: Egg) -> RenderResult:
        """Render Egg records into target file contents.

        Returns a dict of ``filename -> content`` with ``{{SECRET_NNN}}``
        and ``{{PII_NNN}}`` placeholders intact.
        """
        files: dict[str, str] = {}

        # --- PERSONA -> persona.md + identity.md ---
        persona_records: list[MemoryRecord] = []
        identity_records: list[MemoryRecord] = []
        for m in egg.memory.memory:
            if m.label != MemoryLabel.PERSONA:
                continue
            if _is_identity_source(m):
                identity_records.append(m)
            else:
                persona_records.append(m)

        if persona_records:
            files["persona.md"] = _join_records(persona_records)
        if identity_records:
            files["identity.md"] = _join_records(identity_records)

        # --- FLOW -> agents.md ---
        flow_records = [m for m in egg.memory.memory if m.label == MemoryLabel.FLOW]
        if flow_records:
            files["agents.md"] = _join_records(flow_records)

        # --- CONTEXT -> user.md + tools.md ---
        user_records: list[MemoryRecord] = []
        tools_records: list[MemoryRecord] = []
        for m in egg.memory.memory:
            if m.label != MemoryLabel.CONTEXT:
                continue
            if _is_tools_source(m):
                tools_records.append(m)
            else:
                user_records.append(m)

        if user_records:
            files["user.md"] = _join_records(user_records)
        if tools_records:
            files["tools.md"] = _join_records(tools_records)

        # --- STATE -> knowledge.md + memory/YYYY-MM-DD.md ---
        undated_state: list[MemoryRecord] = []
        dated_state: dict[str, list[MemoryRecord]] = defaultdict(list)
        for m in egg.memory.memory:
            if m.label != MemoryLabel.STATE:
                continue
            date_key = _date_key_from_record(m)
            if date_key:
                dated_state[date_key].append(m)
            else:
                undated_state.append(m)

        if undated_state:
            files["knowledge.md"] = _join_records(undated_state)
        for date_key in sorted(dated_state):
            files[f"memory/{date_key}.md"] = _join_records(dated_state[date_key])

        # --- tools/ directory ---
        if egg.skills.skills:
            for skill in egg.skills.skills:
                fname = _skill_to_filename(skill.name)
                files[f"tools/{fname}"] = skill.content + "\n"

        # --- config.toml (credential placeholders + source metadata) ---
        credentials = [
            (s.name, s.placeholder)
            for s in egg.secrets.secrets
            if s.kind == SecretKind.CREDENTIAL
        ]
        source_metadata = egg.manifest.source_metadata or {}
        toml_content = _build_config_toml(credentials, source_metadata)
        if toml_content.strip():
            files["config.toml"] = toml_content

        # --- .zeroclaw/ marker directory ---
        files[".zeroclaw/.keep"] = ""

        # --- mcp/ directory (MCP server configs) ---
        if egg.skills.mcp_configs:
            import json

            for name, cfg in sorted(egg.skills.mcp_configs.items()):
                files[f"mcp/{name}.json"] = (
                    json.dumps(cfg.model_dump(exclude_defaults=True), indent=2) + "\n"
                )

        if not files:
            raise HatchError("Egg produced no output files for ZeroClaw target")

        return RenderResult(files=files, warnings=[])
