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
- mcp/              <- MCP server configs
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from pynydus.api.errors import HatchError
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import (
    Egg,
    MemoryRecord,
)
from pynydus.common.enums import MemoryLabel, SecretKind


def _is_identity_source(rec: MemoryRecord) -> bool:
    """True if this persona record originated from IDENTITY.md."""
    return rec.source_store.lower() in ("identity.md",)


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


def _to_kebab(name: str) -> str:
    """Convert a skill name to kebab-case filename stem."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _join_records(records: list[MemoryRecord]) -> str:
    """Join memory records into a single file's content."""
    return "\n\n".join(r.text for r in records) + "\n"


class OpenClawHatcher:
    """Produce a valid OpenClaw project directory from an Egg."""

    def render(self, egg: Egg) -> RenderResult:
        """Render Egg records into target file contents.

        Returns a dict of ``filename -> content`` with ``{{SECRET_NNN}}``
        and ``{{PII_NNN}}`` placeholders intact. The pipeline handles
        secret substitution and disk I/O.
        """
        files: dict[str, str] = {}

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
            files[f"skills/{stem}.md"] = s.content + "\n"

        # --- config.json (credential placeholders) ---
        credentials = [s for s in egg.secrets.secrets if s.kind == SecretKind.CREDENTIAL]
        if credentials:
            config = {s.name: s.placeholder for s in credentials}
            files["config.json"] = json.dumps(config, indent=2) + "\n"

        # --- mcp/ directory (MCP server configs) ---
        if egg.skills.mcp_configs:
            for name, cfg in sorted(egg.skills.mcp_configs.items()):
                files[f"mcp/{name}.json"] = (
                    json.dumps(cfg.model_dump(exclude_defaults=True), indent=2) + "\n"
                )

        if not files:
            raise HatchError("Egg produced no output files for OpenClaw target")

        return RenderResult(files=files, warnings=warnings)

    def hatch(self, egg: Egg, output_dir: Path) -> HatchResult:
        """Generate OpenClaw project files from an Egg.

        .. deprecated::
            Use :meth:`render` instead. The pipeline now handles disk I/O.
        """
        result = self.render(egg)

        output_dir.mkdir(parents=True, exist_ok=True)
        files_created: list[str] = []
        for fname, content in result.files.items():
            fpath = output_dir / fname
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding='utf-8')
            files_created.append(fname)

        return HatchResult(
            target="openclaw",
            output_dir=output_dir,
            files_created=files_created,
            warnings=list(result.warnings),
        )

    def validate(self, result: HatchResult) -> ValidationReport:
        """Validate generated OpenClaw output."""
        issues: list[ValidationIssue] = []

        has_soul = "soul.md" in result.files_created
        has_skill = "skill.md" in result.files_created
        if not has_soul and not has_skill:
            issues.append(
                ValidationIssue(
                    level="warning",
                    message="Neither soul.md nor skill.md was generated",
                    location=str(result.output_dir),
                )
            )

        for fname in result.files_created:
            fpath = result.output_dir / fname
            if not fpath.exists():
                issues.append(
                    ValidationIssue(
                        level="error",
                        message=f"Expected file not found: {fname}",
                        location=str(fpath),
                    )
                )

        return ValidationReport(
            valid=not any(i.level == "error" for i in issues),
            issues=issues,
        )
