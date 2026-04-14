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
- config.toml          <- credential placeholders + round-tripped manifest fields
- .zeroclaw/           <- marker directory for project detection
- mcp.json             <- MCP servers (Claude Desktop ``mcpServers`` format)

All 4 MemoryLabel values have explicit file mappings.  Records are
fanned back to separate files using ``source_store`` metadata, matching
the structure the spawner reads on ingest.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from pynydus.api.errors import HatchError
from pynydus.api.protocols import Hatcher
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import Egg, HatchResult, MemoryRecord
from pynydus.common.connector_utils import (
    date_key_from_record as _date_key_from_record,
    join_records as _join_records,
)
from pynydus.common.connector_utils import skill_to_filename as _skill_to_filename
from pynydus.common.enums import MemoryLabel, SecretKind


def _is_identity_source(rec: MemoryRecord) -> bool:
    """True if this persona record originated from IDENTITY.md or identity.json."""
    return rec.source_store.lower() in ("identity.md", "identity.json")


def _is_tools_source(rec: MemoryRecord) -> bool:
    """True if this context record originated from TOOLS.md."""
    return rec.source_store.lower() in ("tools.md",)


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_config_toml(
    credentials: list[tuple[str, str]],
    *,
    agent_name: str | None = None,
    agent_description: str | None = None,
    llm_model: str | None = None,
    agent_version: str | None = None,
) -> str:
    """Build a TOML config string from credentials and neutral manifest fields.

    Args:
        credentials: List of ``(name, placeholder)`` pairs for each credential.
        agent_name: Optional agent display name from manifest.
        agent_description: Optional description from manifest.
        llm_model: Optional model id from manifest.
        agent_version: Optional version string (e.g. from spawn metadata).

    Returns:
        TOML-formatted string, or empty string if nothing to write.
    """
    lines: list[str] = []

    if agent_name or llm_model or agent_description or agent_version:
        lines.append("[agent]")
        if agent_name:
            lines.append(f'name = "{_toml_escape(agent_name)}"')
        if llm_model:
            lines.append(f'model = "{_toml_escape(llm_model)}"')
        if agent_description:
            lines.append(f'description = "{_toml_escape(agent_description)}"')
        if agent_version:
            lines.append(f'version = "{_toml_escape(agent_version)}"')
        lines.append("")

    if credentials:
        lines.append("[credentials]")
        for name, placeholder in credentials:
            lines.append(f'{name} = "{placeholder}"')
        lines.append("")

    return "\n".join(lines) + "\n" if lines else ""


class ZeroClawHatcher(Hatcher):
    """Produce a valid ZeroClaw project directory from an Egg."""

    def render(self, egg: Egg, output_dir: Path) -> RenderResult:
        """Render Egg records into ZeroClaw project files.

        Placeholders (``{{SECRET_NNN}}``, ``{{PII_NNN}}``) are preserved.
        the pipeline substitutes real values after this step.

        Args:
            egg: The Egg to render.
            output_dir: Target directory (unused; pipeline performs disk I/O).

        Returns:
            File dict and any warnings produced during rendering.
        """
        _ = output_dir
        files: dict[str, str] = {}
        warnings: list[str] = []

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
                files[f"tools/{fname}"] = skill.body + "\n"

        # --- config.toml (credential placeholders + neutral manifest fields) ---
        credentials = [
            (s.name, s.placeholder) for s in egg.secrets.secrets if s.kind == SecretKind.CREDENTIAL
        ]
        toml_content = _build_config_toml(
            credentials,
            agent_name=egg.manifest.agent_name,
            agent_description=egg.manifest.agent_description,
            llm_model=egg.manifest.llm_model,
        )
        if toml_content.strip():
            files["config.toml"] = toml_content

        # --- .zeroclaw/ marker directory ---
        files[".zeroclaw/.keep"] = ""

        # --- mcp.json (Claude Desktop format) ---
        if egg.mcp.configs:
            mcp_doc = {"mcpServers": dict(egg.mcp.configs)}
            files["mcp.json"] = json.dumps(mcp_doc, indent=2) + "\n"

        if not files:
            raise HatchError("Egg produced no output files for ZeroClaw target")

        return RenderResult(files=files, warnings=warnings)

    def hatch(self, egg: Egg, output_dir: Path) -> HatchResult:
        """Generate ZeroClaw project files from an Egg.

        .. deprecated::
            Use :meth:`render` instead. The pipeline now handles disk I/O.

        Args:
            egg: The Egg to hatch.
            output_dir: Directory where output files are written.

        Returns:
            Result with list of created files and any warnings.
        """
        result = self.render(egg, output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)
        files_created: list[str] = []
        for fname, content in result.files.items():
            fpath = output_dir / fname
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")
            files_created.append(fname)

        marker = output_dir / ".zeroclaw"
        marker.mkdir(exist_ok=True)

        return HatchResult(
            target="zeroclaw",
            output_dir=output_dir,
            files_created=files_created,
            warnings=list(result.warnings),
        )
