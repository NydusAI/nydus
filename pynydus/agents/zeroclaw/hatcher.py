"""ZeroClaw hatcher connector. Spec §11.6.

Produces a valid ZeroClaw project directory from an Egg:
- persona.md      <- memory records labeled "persona"
- agents.md       <- memory records labeled "flow"
- user.md         <- memory records labeled "context"
- knowledge.md    <- memory records labeled "state"
- tools/          <- skill records as Python tool files
- config.json     <- secret placeholders
- mcp/            <- MCP server configs

All 4 MemoryLabel values have explicit file mappings.
"""

from __future__ import annotations

import json

from pynydus.api.errors import HatchError
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import (
    Egg,
    HatchResult,
    ValidationIssue,
    ValidationReport,
)
from pynydus.common.connector_utils import skill_to_filename as _skill_to_filename
from pynydus.common.enums import MemoryLabel, SecretKind


class ZeroClawHatcher:
    """Produce a valid ZeroClaw project directory from an Egg."""

    def render(self, egg: Egg) -> RenderResult:
        """Render Egg records into target file contents.

        Returns a dict of ``filename -> content`` with ``{{SECRET_NNN}}``
        and ``{{PII_NNN}}`` placeholders intact.
        """
        files: dict[str, str] = {}
        warnings: list[str] = []

        # --- persona.md (persona memory) ---
        persona_records = [m for m in egg.memory.memory if m.label == MemoryLabel.PERSONA]
        if persona_records:
            files["persona.md"] = "\n\n".join(r.text for r in persona_records) + "\n"

        # --- agents.md (flow memory) ---
        flow_records = [m for m in egg.memory.memory if m.label == MemoryLabel.FLOW]
        if flow_records:
            files["agents.md"] = "\n\n".join(r.text for r in flow_records) + "\n"

        # --- user.md (context memory) ---
        context_records = [m for m in egg.memory.memory if m.label == MemoryLabel.CONTEXT]
        if context_records:
            files["user.md"] = "\n\n".join(r.text for r in context_records) + "\n"

        # --- knowledge.md (state memory) ---
        state_records = [m for m in egg.memory.memory if m.label == MemoryLabel.STATE]
        if state_records:
            files["knowledge.md"] = "\n\n".join(r.text for r in state_records) + "\n"

        # --- tools/ directory ---
        if egg.skills.skills:
            for skill in egg.skills.skills:
                fname = _skill_to_filename(skill.name)
                files[f"tools/{fname}"] = skill.content + "\n"

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
            raise HatchError("Egg produced no output files for ZeroClaw target")

        return RenderResult(files=files, warnings=warnings)

    def validate(self, result: HatchResult) -> ValidationReport:
        """Validate generated ZeroClaw output."""
        issues: list[ValidationIssue] = []

        has_persona = "persona.md" in result.files_created
        has_tools = any(f.startswith("tools/") for f in result.files_created)
        if not has_persona and not has_tools:
            issues.append(
                ValidationIssue(
                    level="warning",
                    message="Neither persona.md nor tools/ was generated",
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
