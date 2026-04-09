"""OpenClaw hatcher connector. Spec §10.3.

Produces a valid OpenClaw project directory from an Egg:
- soul.md          <- memory records labeled "persona"
- agents.md        <- memory records labeled "flow"
- user.md          <- memory records labeled "context"
- knowledge.md     <- memory records labeled "state"
- skill.md         <- skill records
- config.json      <- secret placeholders
- mcp/             <- MCP server configs

All 4 MemoryLabel values have explicit file mappings.
"""

from __future__ import annotations

import json
from pathlib import Path

from pynydus.api.errors import HatchError
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import (
    Egg,
    HatchResult,
    MemoryLabel,
    SecretKind,
    ValidationIssue,
    ValidationReport,
)


class OpenClawHatcher:
    """Produce a valid OpenClaw project directory from an Egg."""

    def render(self, egg: Egg) -> RenderResult:
        """Render Egg records into target file contents.

        Returns a dict of ``filename -> content`` with ``{{SECRET_NNN}}``
        and ``{{PII_NNN}}`` placeholders intact. The pipeline handles
        secret substitution and disk I/O.
        """
        files: dict[str, str] = {}
        warnings: list[str] = []

        # --- soul.md (persona memory) ---
        persona_records = [
            m for m in egg.memory.memory if m.label == MemoryLabel.PERSONA
        ]
        if persona_records:
            files["soul.md"] = "\n\n".join(r.text for r in persona_records) + "\n"

        # --- agents.md (flow memory) ---
        flow_records = [
            m for m in egg.memory.memory if m.label == MemoryLabel.FLOW
        ]
        if flow_records:
            files["agents.md"] = "\n\n".join(r.text for r in flow_records) + "\n"

        # --- user.md (context memory) ---
        context_records = [
            m for m in egg.memory.memory if m.label == MemoryLabel.CONTEXT
        ]
        if context_records:
            files["user.md"] = "\n\n".join(r.text for r in context_records) + "\n"

        # --- knowledge.md (state memory) ---
        state_records = [
            m for m in egg.memory.memory if m.label == MemoryLabel.STATE
        ]
        if state_records:
            files["knowledge.md"] = "\n\n".join(r.text for r in state_records) + "\n"

        # --- skill.md ---
        if egg.skills.skills:
            sections: list[str] = []
            for s in egg.skills.skills:
                sections.append(f"# {s.name}\n\n{s.content}")
            files["skill.md"] = "\n\n".join(sections) + "\n"

        # --- config.json (credential placeholders) ---
        credentials = [
            s for s in egg.secrets.secrets if s.kind == SecretKind.CREDENTIAL
        ]
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
