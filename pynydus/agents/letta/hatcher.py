"""Letta hatcher connector. Spec §10.3.

Produces a valid Letta AgentFile (.af) from an Egg:
- agent.af  <- single JSON file conforming to AgentFileSchema

The .af file is a self-contained portable format importable by any
Letta server via ``letta.agents.import_file()``.

All 4 MemoryLabel values have explicit mappings:
- PERSONA -> blocks[label="persona"]
- CONTEXT -> blocks[label="human"]
- FLOW    -> agents[0].system
- STATE   -> archival_memory.json (supplemental; .af doesn't support passages yet)
"""

from __future__ import annotations

import json
from pathlib import Path

from pynydus.api.errors import HatchError
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import Egg, HatchResult, ValidationIssue, ValidationReport
from pynydus.common.enums import MemoryLabel, SecretKind


class LettaHatcher:
    """Produce a valid Letta AgentFile (.af) from an Egg."""

    def render(self, egg: Egg) -> RenderResult:
        """Render Egg records into an AgentFileSchema-shaped .af file.

        Returns a dict of ``filename -> content`` with ``{{SECRET_NNN}}``
        and ``{{PII_NNN}}`` placeholders intact.
        """
        files: dict[str, str] = {}
        warnings: list[str] = []

        blocks: list[dict] = []
        block_ids: list[str] = []
        tools: list[dict] = []
        tool_ids: list[str] = []

        # --- blocks from PERSONA and CONTEXT memory ---
        block_idx = 0
        persona_texts: list[str] = []
        human_texts: list[str] = []

        for mem_rec in egg.memory.memory:
            if mem_rec.label == MemoryLabel.PERSONA:
                persona_texts.append(mem_rec.text)
            elif mem_rec.label == MemoryLabel.CONTEXT:
                human_texts.append(mem_rec.text)

        if persona_texts:
            bid = f"block-{block_idx}"
            blocks.append(
                {
                    "id": bid,
                    "label": "persona",
                    "value": "\n\n".join(persona_texts),
                    "limit": 5000,
                    "is_template": False,
                    "read_only": False,
                    "description": None,
                    "metadata": {},
                }
            )
            block_ids.append(bid)
            block_idx += 1

        if human_texts:
            bid = f"block-{block_idx}"
            blocks.append(
                {
                    "id": bid,
                    "label": "human",
                    "value": "\n\n".join(human_texts),
                    "limit": 5000,
                    "is_template": False,
                    "read_only": False,
                    "description": None,
                    "metadata": {},
                }
            )
            block_ids.append(bid)
            block_idx += 1

        # --- system prompt from FLOW memory ---
        flow_records = [m for m in egg.memory.memory if m.label == MemoryLabel.FLOW]
        system_prompt = "\n\n".join(r.text for r in flow_records) if flow_records else ""

        # --- tools from skills ---
        for i, skill in enumerate(egg.skills.skills):
            tid = f"tool-{i}"
            tools.append(
                {
                    "id": tid,
                    "name": _skill_to_module_name(skill.name),
                    "description": f"Custom tool: {skill.name}",
                    "source_code": skill.content,
                    "source_type": "python",
                    "tool_type": "custom",
                    "tags": [],
                    "json_schema": {
                        "name": _skill_to_module_name(skill.name),
                        "description": f"Custom tool: {skill.name}",
                        "parameters": {"type": "object", "properties": {}, "required": []},
                    },
                    "return_char_limit": 50000,
                }
            )
            tool_ids.append(tid)

        # --- credential placeholders -> tool_exec_environment_variables ---
        env_vars: dict[str, str] = {}
        credentials = [s for s in egg.secrets.secrets if s.kind == SecretKind.CREDENTIAL]
        for cred in credentials:
            env_vars[cred.name] = cred.placeholder

        # --- round-trip LLM config from source metadata ---
        llm_config: dict | None = None
        embedding_config: dict | None = None
        source_meta = egg.manifest.source_metadata or {}
        if any(k.startswith("letta.llm.") for k in source_meta):
            llm_config = {}
            for k, v in source_meta.items():
                if k.startswith("letta.llm."):
                    field = k.removeprefix("letta.llm.")
                    llm_config[field] = v
        if any(k.startswith("letta.embedding.") for k in source_meta):
            embedding_config = {}
            for k, v in source_meta.items():
                if k.startswith("letta.embedding."):
                    field = k.removeprefix("letta.embedding.")
                    embedding_config[field] = v

        # --- build agent dict ---
        agent: dict = {
            "id": "agent-0",
            "name": source_meta.get("letta.name", "nydus_agent"),
            "system": system_prompt,
            "agent_type": source_meta.get("letta.agent_type", "letta_v1_agent"),
            "block_ids": block_ids,
            "tool_ids": tool_ids,
            "tool_rules": [],
            "tags": [],
            "messages": [],
            "in_context_message_ids": [],
            "files_agents": [],
            "group_ids": [],
            "tool_exec_environment_variables": env_vars,
            "include_base_tools": False,
            "include_multi_agent_tools": False,
            "include_base_tool_rules": False,
            "include_default_source": False,
            "message_buffer_autoclear": False,
            "enable_sleeptime": False,
        }
        if llm_config:
            agent["llm_config"] = llm_config
        if embedding_config:
            agent["embedding_config"] = embedding_config

        # --- mcp_servers ---
        mcp_servers: list[dict] = []
        if egg.skills.mcp_configs:
            for name, cfg in sorted(egg.skills.mcp_configs.items()):
                srv = cfg.model_dump(exclude_defaults=True)
                srv.setdefault("server_name", name)
                mcp_servers.append(srv)

        # --- build AgentFileSchema ---
        af_schema: dict = {
            "agents": [agent],
            "groups": [],
            "blocks": blocks,
            "files": [],
            "sources": [],
            "tools": tools,
            "mcp_servers": mcp_servers,
            "metadata": {
                "nydus_source": egg.manifest.agent_type.value,
                "nydus_version": egg.manifest.nydus_version,
            },
        }

        files["agent.af"] = json.dumps(af_schema, indent=2) + "\n"

        # --- archival_memory.json (STATE memory, supplemental) ---
        # .af doesn't support archival passages yet (on Letta roadmap)
        state_records = [m for m in egg.memory.memory if m.label == MemoryLabel.STATE]
        if state_records:
            entries = []
            for rec in state_records:
                entry: dict[str, str | None] = {"text": rec.text}
                entry["timestamp"] = rec.timestamp.isoformat() if rec.timestamp else None
                entries.append(entry)
            files["archival_memory.json"] = json.dumps(entries, indent=2) + "\n"

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
            fpath.write_text(content, encoding="utf-8")
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
