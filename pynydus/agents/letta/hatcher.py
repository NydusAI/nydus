"""Letta hatcher connector. Spec §10.3.

Produces a valid Letta agent project directory from an Egg:
- agent_state.json     <- memory blocks + agent config skeleton
- tools/               <- skill records as Python tool files
- archival_memory.json <- state memory
- system_prompt.md     <- flow memory

All 4 MemoryLabel values have explicit mappings:
- PERSONA -> memory.persona block in agent_state.json
- CONTEXT -> memory.human block in agent_state.json
- FLOW    -> system field + system_prompt.md
- STATE   -> archival_memory.json
"""

from __future__ import annotations

import json

from pynydus.api.errors import HatchError
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import Egg
from pynydus.common.connector_utils import skill_to_filename as _skill_to_filename
from pynydus.common.enums import MemoryLabel, SecretKind

_LABEL_TO_BLOCK: dict[MemoryLabel, str] = {
    MemoryLabel.PERSONA: "persona",
    MemoryLabel.CONTEXT: "human",
    MemoryLabel.FLOW: "system",
}


class LettaHatcher:
    """Produce a valid Letta agent directory from an Egg."""

    def render(self, egg: Egg) -> RenderResult:
        """Render Egg records into target file contents.

        Returns a dict of ``filename -> content`` with ``{{SECRET_NNN}}``
        and ``{{PII_NNN}}`` placeholders intact.
        """
        files: dict[str, str] = {}

        # --- agent_state.json ---
        agent_state = self._build_agent_state(egg)
        files["agent_state.json"] = json.dumps(agent_state, indent=2) + "\n"

        # --- system_prompt.md ---
        system_records = [m for m in egg.memory.memory if m.label == MemoryLabel.FLOW]
        if system_records:
            files["system_prompt.md"] = "\n\n".join(r.text for r in system_records) + "\n"

        # --- tools/ directory ---
        if egg.skills.skills:
            for skill in egg.skills.skills:
                fname = _skill_to_filename(skill.name)
                files[f"tools/{fname}"] = skill.content + "\n"

        # --- archival_memory.json (state) ---
        state_records = [m for m in egg.memory.memory if m.label == MemoryLabel.STATE]
        if state_records:
            entries = []
            for rec in state_records:
                entry: dict[str, str | None] = {"text": rec.text}
                entry["timestamp"] = rec.timestamp.isoformat() if rec.timestamp else None
                entries.append(entry)
            files["archival_memory.json"] = json.dumps(entries, indent=2) + "\n"

        # --- .letta/config.json (credential placeholders) ---
        credentials = [s for s in egg.secrets.secrets if s.kind == SecretKind.CREDENTIAL]
        if credentials:
            config = {s.name: s.placeholder for s in credentials}
            files[".letta/config.json"] = json.dumps(config, indent=2) + "\n"

        if not files:
            raise HatchError("Egg produced no output files for Letta target")

        return RenderResult(files=files, warnings=warnings)

    def hatch(self, egg: Egg, output_dir: Path) -> HatchResult:
        """Generate Letta project files from an Egg.

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
            target="letta",
            output_dir=output_dir,
            files_created=files_created,
            warnings=list(result.warnings),
        )

    def validate(self, result: HatchResult) -> ValidationReport:
        """Validate generated Letta output."""
        issues: list[ValidationIssue] = []

        if "agent_state.json" not in result.files_created:
            issues.append(
                ValidationIssue(
                    level="warning",
                    message="agent_state.json was not generated",
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

        state_path = result.output_dir / "agent_state.json"
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text())
                if not isinstance(data, dict):
                    issues.append(
                        ValidationIssue(
                            level="error",
                            message="agent_state.json is not a JSON object",
                            location=str(state_path),
                        )
                    )
                elif "memory" not in data and "system" not in data:
                    issues.append(
                        ValidationIssue(
                            level="warning",
                            message="agent_state.json has no memory blocks or system prompt",
                            location=str(state_path),
                        )
                    )
            except json.JSONDecodeError:
                issues.append(
                    ValidationIssue(
                        level="error",
                        message="agent_state.json is not valid JSON",
                        location=str(state_path),
                    )
                )

        return ValidationReport(
            valid=not any(i.level == "error" for i in issues),
            issues=issues,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_agent_state(self, egg: Egg) -> dict:
        """Build the agent_state.json content from Egg data."""
        state: dict = {
            "name": "nydus_agent",
            "memory": {},
            "tools": [],
        }

        for mem_rec in egg.memory.memory:
            if mem_rec.label in _LABEL_TO_BLOCK:
                block_name = _LABEL_TO_BLOCK[mem_rec.label]
                if block_name in state["memory"]:
                    state["memory"][block_name]["value"] += "\n\n" + mem_rec.text
                else:
                    state["memory"][block_name] = {
                        "value": mem_rec.text,
                        "limit": 5000,
                    }

        flow_records = [m for m in egg.memory.memory if m.label == MemoryLabel.FLOW]
        if flow_records:
            state["system"] = "\n\n".join(r.text for r in flow_records)

        for skill in egg.skills.skills:
            state["tools"].append(
                {
                    "name": _skill_to_module_name(skill.name),
                    "source_code": skill.content,
                }
            )

        if egg.manifest.source_metadata:
            state["metadata"] = {
                "nydus_source": egg.manifest.agent_type.value,
                "nydus_version": egg.manifest.nydus_version,
            }

        return state


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _skill_to_module_name(name: str) -> str:
    """Convert a skill display name to a Python module name."""
    module = name.lower().strip().replace(" ", "_").replace("-", "_")
    module = "".join(c for c in module if c.isalnum() or c == "_")
    if module and module[0].isdigit():
        module = f"tool_{module}"
    return module or "tool"
