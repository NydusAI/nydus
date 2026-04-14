"""Letta spawner connector. Spec §10.3.

Parses a Letta agent export directory, database dump, or .af AgentFile:
- *.af (AgentFile) -> Letta's official portable agent format (AgentFileSchema)
- agent_state.json  -> memory blocks (persona, human, system) + agent config
- archival_memory.json / archival/ -> long-term archival memory records
- tools/ -> Python tool definitions -> skill records
- system_prompt.md -> system prompt -> memory record
- .letta/ marker directory (optional)

Also supports reading from a Letta SQLite database file (agent.db) as a
fallback when structured JSON exports are not available.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pynydus.api.errors import ConnectorError
from pynydus.api.protocols import Spawner
from pynydus.api.raw_types import (
    ParseResult,
    RawMemory,
    RawSkill,
)
from pynydus.common.connector_utils import (
    parse_mcp_configs_from_files as _parse_mcp_configs_from_files,
)
from pynydus.common.connector_utils import (
    parse_timestamp as _parse_timestamp,
)
from pynydus.common.enums import MemoryLabel

_AGENT_STATE_FILES = ("agent_state.json",)
_ARCHIVAL_FILES = ("archival_memory.json",)
_SYSTEM_PROMPT_FILES = ("system_prompt.md", "system_prompt.txt")
_DB_FILES = ("agent.db",)

_BLOCK_LABEL_MAP: dict[str, MemoryLabel] = {
    "persona": MemoryLabel.PERSONA,
    "soul": MemoryLabel.PERSONA,
    "human": MemoryLabel.CONTEXT,
    "about_user": MemoryLabel.CONTEXT,
    "preferences": MemoryLabel.CONTEXT,
    "system": MemoryLabel.FLOW,
    "custom_instructions": MemoryLabel.FLOW,
    "scratchpad": MemoryLabel.STATE,
    "active_hypotheses": MemoryLabel.STATE,
    "conversation_patterns": MemoryLabel.STATE,
    "learned_corrections": MemoryLabel.STATE,
}

FILE_PATTERNS = [
    "*.json",
    "*.md",
    "*.txt",
    "*.yaml",
    "*.yml",
    "*.af",
    "tools/*.py",
    "archival/*.txt",
    "archival/*.md",
    "archival/*.json",
    ".letta/*.json",
]
"""Glob patterns the pipeline uses to read source files from disk."""


def _extract_af_llm_embedding(agent: dict) -> tuple[str | None, int | None, str | None]:
    """Read neutral LLM / embedding fields from an AgentFile ``agent`` dict."""
    llm_model = None
    llm_context_window = None
    embedding_model = None
    llm = agent.get("llm_config", {})
    if isinstance(llm, dict):
        m = llm.get("model")
        if m is not None:
            llm_model = str(m)
        cw = llm.get("context_window")
        if cw is not None:
            try:
                llm_context_window = int(cw)
            except (TypeError, ValueError):
                llm_context_window = None
    emb = agent.get("embedding_config", {})
    if isinstance(emb, dict):
        em = emb.get("embedding_model")
        if em is not None:
            embedding_model = str(em)
    return llm_model, llm_context_window, embedding_model


class LettaSpawner(Spawner):
    """Parse a Letta agent export directory, database, or AgentFile."""

    FILE_PATTERNS = FILE_PATTERNS

    def parse(self, files: dict[str, str]) -> ParseResult:
        """Parse pre-redacted file contents into raw skills and memory.

        Args:
            files: ``filename -> UTF-8 content`` (already redacted). DB-mode
                may use synthetic keys such as ``_db_tables.json``.

        Returns:
            Skills, memory, and MCP configs.
        """
        af_result = self._try_parse_agent_file(files)
        if af_result is not None:
            return af_result

        skills = self._parse_skills(files)
        memories = self._parse_memories(files)
        mcp_configs = self._parse_mcp_configs(files)
        return ParseResult(
            skills=skills,
            memory=memories,
            mcp_configs=mcp_configs,
        )

    def parse_db(
        self, db_path: Path, supplemental_files: dict[str, str] | None = None
    ) -> ParseResult:
        """Parse directly from a Letta SQLite database.

        This is the special case for DB-mode extraction. The pipeline calls
        this instead of ``parse()`` when the source is a ``.db`` file.

        Args:
            db_path: Path to the Letta ``agent.db`` SQLite file.
            supplemental_files: Additional text files to parse alongside the DB.

        Returns:
            Skills and memory extracted from database tables.
        """
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise ConnectorError(f"Cannot open Letta database: {exc}") from exc

        skills: list[RawSkill] = []
        memories: list[RawMemory] = []

        try:
            tables = self._get_tables(conn)
            if "blocks" in tables:
                for row in conn.execute("SELECT * FROM blocks ORDER BY rowid").fetchall():
                    row_dict = dict(row)
                    text = row_dict.get("value", row_dict.get("text", ""))
                    if text and isinstance(text, str):
                        label_key = row_dict.get("label", row_dict.get("name", ""))
                        label = _BLOCK_LABEL_MAP.get(label_key, MemoryLabel.CONTEXT)
                        memories.append(
                            RawMemory(
                                text=text.strip(),
                                source_file=f"db.blocks.{label_key}",
                                label=label,
                            )
                        )
            if "archival_memory" in tables:
                for row in conn.execute("SELECT * FROM archival_memory ORDER BY rowid").fetchall():
                    text = dict(row).get("text", "")
                    if text and isinstance(text, str):
                        memories.append(
                            RawMemory(
                                text=text.strip(),
                                source_file="db.archival_memory",
                                label=MemoryLabel.STATE,
                            )
                        )
            if "tools" in tables:
                for row in conn.execute("SELECT * FROM tools ORDER BY rowid").fetchall():
                    row_dict = dict(row)
                    name = row_dict.get("name", "unnamed_tool")
                    source = row_dict.get("source_code", row_dict.get("json_schema", ""))
                    if source:
                        skills.append(
                            RawSkill(
                                name=_python_module_display_name(name),
                                content=source if isinstance(source, str) else json.dumps(source),
                                source_file="agent.db",
                            )
                        )
        finally:
            conn.close()

        return ParseResult(skills=skills, memory=memories)

    # ---------------------------------------------------------------------------
    # AgentFile (.af) parsing: real AgentFileSchema
    # ---------------------------------------------------------------------------

    def _try_parse_agent_file(self, files: dict[str, str]) -> ParseResult | None:
        """Try to parse a .af AgentFile from the files dict.

        Handles the real AgentFileSchema with top-level ``agents``,
        ``blocks``, ``tools``, ``mcp_servers``, ``skills``, ``metadata``.
        """
        af_content = None
        af_name = None
        for key, content in files.items():
            if key.endswith(".af"):
                af_content = content
                af_name = key
                break
        if af_content is None:
            return None

        try:
            data = json.loads(af_content)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        # Must have top-level "agents" key per AgentFileSchema
        if "agents" not in data or not isinstance(data["agents"], list):
            return None

        agents = data["agents"]
        if not agents:
            return None
        agent = agents[0]
        if not isinstance(agent, dict):
            return None

        skills: list[RawSkill] = []
        memories: list[RawMemory] = []
        mcp_configs: dict[str, dict] = {}

        # --- blocks (top-level list) ---
        self._parse_af_blocks(data, memories, af_name)

        # --- system prompt (from agent) ---
        self._parse_af_system_prompt(agent, memories, af_name)

        # --- tools (top-level list, filtered by tool_type) ---
        self._parse_af_tools(data, skills, af_name)

        # --- skills (top-level list, SkillSchema with files/source_url) ---
        self._parse_af_skills(data, skills, af_name)

        # --- tool_rules (from agent) ---
        self._parse_af_tool_rules(agent, memories, af_name)

        # --- messages (from agent, content is list of objects) ---
        self._parse_af_messages(agent, memories, af_name)

        # --- env vars (from agent) ---
        self._parse_af_env_vars(agent, memories, af_name)

        # --- mcp_servers (top-level) ---
        self._parse_af_mcp_servers(data, mcp_configs)

        llm_model, llm_context_window, embedding_model = _extract_af_llm_embedding(agent)
        agent_name = agent.get("name") if isinstance(agent.get("name"), str) else None
        agent_description = agent.get("description") if isinstance(agent.get("description"), str) else None

        extra_lines: list[str] = []
        atype = agent.get("agent_type")
        if isinstance(atype, str) and atype:
            extra_lines.append(f"agent_type={atype}")
        tags = agent.get("tags")
        if isinstance(tags, list) and tags:
            tag_str = ",".join(str(t) for t in tags if t is not None)
            if tag_str:
                extra_lines.append(f"tags={tag_str}")
        if extra_lines:
            suffix = "\n" + "\n".join(extra_lines)
            agent_description = (agent_description or "") + suffix

        return ParseResult(
            skills=skills,
            memory=memories,
            mcp_configs=mcp_configs,
            agent_name=agent_name,
            agent_description=agent_description,
            llm_model=llm_model,
            llm_context_window=llm_context_window,
            embedding_model=embedding_model,
        )

    @staticmethod
    def _parse_af_blocks(data: dict, memories: list[RawMemory], af_name: str | None) -> None:
        """Parse top-level ``blocks`` list from AgentFileSchema."""
        blocks = data.get("blocks", [])
        if not isinstance(blocks, list):
            return
        for block in blocks:
            if not isinstance(block, dict):
                continue
            label_key = block.get("label", "")
            text = _extract_block_text(block)
            if not text:
                continue
            label = _BLOCK_LABEL_MAP.get(label_key, MemoryLabel.CONTEXT)
            memories.append(
                RawMemory(
                    text=text,
                    source_file=f"{af_name}#blocks.{label_key}",
                    label=label,
                )
            )

    @staticmethod
    def _parse_af_system_prompt(
        agent: dict, memories: list[RawMemory], af_name: str | None
    ) -> None:
        """Parse ``system`` field from the agent dict."""
        system = agent.get("system", "")
        if system and isinstance(system, str):
            memories.append(
                RawMemory(
                    text=system.strip(),
                    source_file=f"{af_name}#system",
                    label=MemoryLabel.FLOW,
                )
            )

    @staticmethod
    def _parse_af_tools(data: dict, skills: list[RawSkill], af_name: str | None) -> None:
        """Parse top-level ``tools`` list.

        Only custom tools (with ``source_code``) become skill records.
        Built-in Letta tools (letta_core, letta_builtin, letta_sleeptime_core)
        have ``source_code: null`` and are skipped.
        """
        tools = data.get("tools", [])
        if not isinstance(tools, list):
            return
        for tool_def in tools:
            if not isinstance(tool_def, dict):
                continue
            tname = tool_def.get("name", "")
            tsource = tool_def.get("source_code")
            if not tsource or not isinstance(tsource, str):
                continue
            skills.append(
                RawSkill(
                    name=_python_module_display_name(tname) if tname else "unnamed_tool",
                    content=tsource,
                    source_file=af_name or ".af",
                )
            )

    @staticmethod
    def _parse_af_skills(data: dict, skills: list[RawSkill], af_name: str | None) -> None:
        """Parse top-level ``skills`` list (SkillSchema objects).

        Each skill has ``name``, optional ``files`` dict (must include
        ``SKILL.md``), and optional ``source_url``.
        """
        af_skills = data.get("skills", [])
        if not isinstance(af_skills, list):
            return
        seen = {s.name for s in skills}
        for skill_def in af_skills:
            if not isinstance(skill_def, dict):
                continue
            name = skill_def.get("name", "")
            if not name or name in seen:
                continue
            skill_files = skill_def.get("files") or {}
            content = skill_files.get("SKILL.md", "")
            if not content:
                source_url = skill_def.get("source_url", "")
                content = f"[skill reference: {source_url}]" if source_url else ""
            if content:
                skills.append(
                    RawSkill(
                        name=name,
                        content=content.strip(),
                        source_file=f"{af_name}#skills.{name}",
                    )
                )
                seen.add(name)

    @staticmethod
    def _parse_af_tool_rules(agent: dict, memories: list[RawMemory], af_name: str | None) -> None:
        """Parse ``tool_rules`` from the agent dict as FLOW memory."""
        rules = agent.get("tool_rules", [])
        if not isinstance(rules, list) or not rules:
            return
        rule_texts = []
        for rule in rules:
            if isinstance(rule, dict):
                rule_texts.append(json.dumps(rule))
            elif isinstance(rule, str):
                rule_texts.append(rule)
        if rule_texts:
            memories.append(
                RawMemory(
                    text="\n".join(rule_texts),
                    source_file=f"{af_name}#tool_rules",
                    label=MemoryLabel.FLOW,
                )
            )

    @staticmethod
    def _parse_af_messages(agent: dict, memories: list[RawMemory], af_name: str | None) -> None:
        """Parse ``messages`` from agent dict as STATE memory.

        Message ``content`` is a list of ``{type, text}`` objects in
        AgentFileSchema, not a plain string.
        """
        messages = agent.get("messages", [])
        if not isinstance(messages, list):
            return
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "")
            # Skip system messages (already captured via system prompt)
            if role == "system":
                continue
            text = _extract_message_text(msg)
            if not text:
                continue
            ts = _parse_timestamp(msg.get("created_at", msg.get("timestamp")))
            memories.append(
                RawMemory(
                    text=text.strip(),
                    source_file=f"{af_name}#messages.{role}",
                    label=MemoryLabel.STATE,
                    timestamp=ts,
                )
            )

    @staticmethod
    def _parse_af_env_vars(agent: dict, memories: list[RawMemory], af_name: str | None) -> None:
        """Parse ``tool_exec_environment_variables`` from agent dict.

        After redaction these become SECRET placeholders. We store them as
        CONTEXT memory so the pipeline secret scan can replace the raw values
        with ``{{SECRET_NNN}}`` placeholders.
        """
        env_vars = agent.get(
            "tool_exec_environment_variables",
            agent.get("env_vars", agent.get("environment_variables", {})),
        )
        if not isinstance(env_vars, dict) or not env_vars:
            return
        lines = [f"{k}={v}" for k, v in env_vars.items() if isinstance(v, str)]
        if lines:
            memories.append(
                RawMemory(
                    text="\n".join(lines),
                    source_file=f"{af_name}#env_vars",
                    label=MemoryLabel.CONTEXT,
                )
            )

    @staticmethod
    def _parse_af_mcp_servers(data: dict, mcp_configs: dict[str, dict]) -> None:
        """Parse top-level ``mcp_servers`` list."""
        servers = data.get("mcp_servers", [])
        if not isinstance(servers, list):
            return
        for srv in servers:
            if not isinstance(srv, dict):
                continue
            name = srv.get("server_name", srv.get("name", ""))
            if name:
                mcp_configs[name] = srv

    # ---------------------------------------------------------------------------
    # Parse helpers (operate on file dict, not filesystem)
    # ---------------------------------------------------------------------------

    def _parse_skills(self, files: dict[str, str]) -> list[RawSkill]:
        """Parse skills from file contents dict."""
        skills: list[RawSkill] = []

        for key, content in sorted(files.items()):
            if key.startswith("tools/") and key.endswith(".py"):
                content = content.strip()
                if content:
                    stem = key.removeprefix("tools/").removesuffix(".py")
                    skills.append(
                        RawSkill(
                            name=_python_module_display_name(stem),
                            content=content,
                            source_file=key,
                        )
                    )

        state = _load_agent_state_from_files(files)
        if state:
            names_on_disk = {s.name for s in skills}
            for tool_def in state.get("tools", []):
                if isinstance(tool_def, dict):
                    tname = tool_def.get("name", "")
                    tsource = tool_def.get("source_code", "")
                    display = _python_module_display_name(tname) if tname else tname
                    if display not in names_on_disk and tsource:
                        skills.append(
                            RawSkill(
                                name=display or "unnamed_tool",
                                content=tsource,
                                source_file="agent_state.json",
                            )
                        )
        return skills

    def _parse_memories(self, files: dict[str, str]) -> list[RawMemory]:
        """Parse memories from agent state, system prompt, and archival memory."""
        memories: list[RawMemory] = []
        state = _load_agent_state_from_files(files)
        has_system = False

        if state:
            system_text = state.get("system", "")
            if system_text and isinstance(system_text, str):
                memories.append(
                    RawMemory(
                        text=system_text.strip(),
                        source_file="agent_state.json",
                        label=MemoryLabel.FLOW,
                    )
                )
                has_system = True
            mem_blocks = state.get("memory", {})
            if isinstance(mem_blocks, dict):
                for block_name, block_value in mem_blocks.items():
                    text = _extract_block_text(block_value)
                    if text:
                        label = _BLOCK_LABEL_MAP.get(block_name, MemoryLabel.CONTEXT)
                        memories.append(
                            RawMemory(
                                text=text,
                                source_file=f"agent_state.json#memory.{block_name}",
                                label=label,
                            )
                        )

        if not has_system:
            for fname in _SYSTEM_PROMPT_FILES:
                content = files.get(fname, "").strip()
                if content:
                    memories.append(
                        RawMemory(
                            text=content,
                            source_file=fname,
                            label=MemoryLabel.FLOW,
                        )
                    )
                    break

        for fname in _ARCHIVAL_FILES:
            content = files.get(fname, "")
            if not content:
                continue
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                continue
            entries = data if isinstance(data, list) else data.get("entries", [])
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                text = entry.get("text", "").strip()
                if text:
                    ts = _parse_timestamp(entry.get("timestamp"))
                    memories.append(
                        RawMemory(
                            text=text,
                            source_file=fname,
                            label=MemoryLabel.STATE,
                            timestamp=ts,
                        )
                    )

        for key, content in sorted(files.items()):
            if not key.startswith("archival/"):
                continue
            if key.endswith((".txt", ".md")):
                text = content.strip()
                if text:
                    memories.append(
                        RawMemory(
                            text=text,
                            source_file=key,
                            label=MemoryLabel.STATE,
                        )
                    )
            elif key.endswith(".json"):
                try:
                    entries = json.loads(content)
                except json.JSONDecodeError:
                    continue
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, dict):
                            text = entry.get("text", "").strip()
                        elif isinstance(entry, str):
                            text = entry.strip()
                        else:
                            continue
                        if text:
                            memories.append(
                                RawMemory(
                                    text=text,
                                    source_file=key,
                                    label=MemoryLabel.STATE,
                                )
                            )

        return memories

    @staticmethod
    def _parse_mcp_configs(files: dict[str, str]) -> dict[str, dict]:
        return _parse_mcp_configs_from_files(files)

    # ---------------------------------------------------------------------------
    # Database helpers
    # ---------------------------------------------------------------------------

    @staticmethod
    def _get_tables(conn: sqlite3.Connection) -> set[str]:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in cursor.fetchall()}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _load_agent_state_from_files(files: dict[str, str]) -> dict | None:
    """Load agent_state.json from a file dict."""
    for fname in _AGENT_STATE_FILES:
        content = files.get(fname, "")
        if content:
            try:
                data = json.loads(content)
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _extract_block_text(block_value: object) -> str:
    """Extract text from a memory block value (string or dict with value/text)."""
    if isinstance(block_value, str):
        return block_value.strip()
    if isinstance(block_value, dict):
        return (block_value.get("value", "") or block_value.get("text", "")).strip()
    return ""


def _extract_message_text(msg: dict) -> str:
    """Extract text from a message.

    In AgentFileSchema, ``content`` is a list of ``{type, text}`` objects.
    Falls back to plain string for legacy formats.
    """
    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if text and isinstance(text, str):
                    parts.append(text.strip())
            elif isinstance(item, str):
                parts.append(item.strip())
        return "\n\n".join(parts)
    if isinstance(content, str):
        return content.strip()
    text = msg.get("text", "")
    return text.strip() if isinstance(text, str) else ""


def _python_module_display_name(stem: str) -> str:
    """Convert a Python module name to a display name (e.g., search_web -> search web)."""
    return stem.replace("_", " ").replace("-", " ").strip()
