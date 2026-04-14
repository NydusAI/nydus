"""OpenClaw hatcher connector. Spec §10.3.

Produces a valid OpenClaw workspace directory from an Egg, matching
the canonical layout defined in AGENT_SPEC.md:

- SOUL.md           <- persona memory (minus IDENTITY records)
- IDENTITY.md       <- persona memory originating from IDENTITY.md
- AGENTS.md         <- flow memory
- USER.md           <- context memory (minus TOOLS records)
- TOOLS.md          <- context memory originating from TOOLS.md
- MEMORY.md         <- undated state memory
- memory/YYYY-MM-DD.md <- dated state memory (one file per day)
- skills/<name>.md  <- one file per skill, kebab-case names
- config.json       <- secret placeholders
- mcp.json          <- MCP servers (Claude Desktop ``mcpServers`` format)
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from pynydus.api.errors import HatchError
from pynydus.api.protocols import Hatcher
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import (
    Egg,
    HatchResult,
    MemoryRecord,
)
from pynydus.common.connector_utils import (
    date_key_from_record as _date_key_from_record,
)
from pynydus.common.connector_utils import (
    join_records as _join_records,
)
from pynydus.common.enums import MemoryLabel, SecretKind


def _is_identity_source(rec: MemoryRecord) -> bool:
    """True if this persona record originated from IDENTITY.md."""
    return rec.source_store.lower() in ("identity.md",)


def _is_tools_source(rec: MemoryRecord) -> bool:
    """True if this context record originated from TOOLS.md."""
    return rec.source_store.lower() in ("tools.md",)


def _to_kebab(name: str) -> str:
    """Convert a skill name to kebab-case filename stem."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class OpenClawHatcher(Hatcher):
    """Produce a valid OpenClaw project directory from an Egg."""

    def render(self, egg: Egg, output_dir: Path) -> RenderResult:
        """Render Egg records into OpenClaw project files.

        Placeholders (``{{SECRET_NNN}}``, ``{{PII_NNN}}``) are preserved.
        the pipeline substitutes real values after this step.

        Args:
            egg: The Egg to render.
            output_dir: Target directory (unused, pipeline performs disk I/O).

        Returns:
            File dict and any warnings produced during rendering.
        """
        _ = output_dir
        files: dict[str, str] = {}
        warnings: list[str] = []

        # --- PERSONA -> SOUL.md + IDENTITY.md ---
        soul_records: list[MemoryRecord] = []
        identity_records: list[MemoryRecord] = []
        for m in egg.memory.memory:
            if m.label != MemoryLabel.PERSONA:
                continue
            if _is_identity_source(m):
                identity_records.append(m)
            else:
                soul_records.append(m)

        if soul_records:
            files["SOUL.md"] = _join_records(soul_records)
        if identity_records:
            files["IDENTITY.md"] = _join_records(identity_records)

        # --- FLOW -> AGENTS.md ---
        flow_records = [m for m in egg.memory.memory if m.label == MemoryLabel.FLOW]
        if flow_records:
            files["AGENTS.md"] = _join_records(flow_records)

        # --- CONTEXT -> USER.md + TOOLS.md ---
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
            files["USER.md"] = _join_records(user_records)
        if tools_records:
            files["TOOLS.md"] = _join_records(tools_records)

        # --- STATE -> MEMORY.md + memory/YYYY-MM-DD.md ---
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
            files["MEMORY.md"] = _join_records(undated_state)
        for date_key in sorted(dated_state):
            files[f"memory/{date_key}.md"] = _join_records(dated_state[date_key])

        # --- skills/<name>.md ---
        for s in egg.skills.skills:
            stem = _to_kebab(s.name)
            files[f"skills/{stem}.md"] = s.body + "\n"

        # --- config.json (credential placeholders) ---
        credentials = [s for s in egg.secrets.secrets if s.kind == SecretKind.CREDENTIAL]
        if credentials:
            config = {s.name: s.placeholder for s in credentials}
            files["config.json"] = json.dumps(config, indent=2) + "\n"

        # --- mcp.json (Claude Desktop format) ---
        if egg.mcp.configs:
            mcp_doc = {"mcpServers": dict(egg.mcp.configs)}
            files["mcp.json"] = json.dumps(mcp_doc, indent=2) + "\n"

        if not files:
            raise HatchError("Egg produced no output files for OpenClaw target")

        return RenderResult(files=files, warnings=warnings)

    def hatch(self, egg: Egg, output_dir: Path) -> HatchResult:
        """Generate OpenClaw project files from an Egg.

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

        return HatchResult(
            target="openclaw",
            output_dir=output_dir,
            files_created=files_created,
            warnings=list(result.warnings),
        )
