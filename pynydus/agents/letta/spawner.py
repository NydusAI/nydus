"""Letta spawner connector. Spec §10.3.

Parses a Letta agent export directory, database dump, or .af AgentFile:
- agent_state.json  -> memory blocks (persona, human, system) + agent config
- archival_memory.json / archival/ -> long-term archival memory records
- tools/ -> Python tool definitions -> skill records
- system_prompt.md -> system prompt -> memory record
- .letta/ marker directory (optional)
- *.af (AgentFile) -> Letta's official portable agent format

Also supports reading from a Letta SQLite database file (agent.db) as a
fallback when structured JSON exports are not available.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pynydus.api.errors import ConnectorError
from pynydus.api.raw_types import (
    ParseResult,
    RawMemory,
    RawSkill,
)
from pynydus.api.schemas import (
    MemoryLabel,
    ValidationIssue,
    ValidationReport,
)
from pynydus.pkg.connector_utils import (
    parse_mcp_configs_from_files as _parse_mcp_configs_from_files,
    parse_timestamp as _parse_timestamp,
)

_AGENT_STATE_FILES = ("agent_state.json",)
_ARCHIVAL_FILES = ("archival_memory.json",)
_SYSTEM_PROMPT_FILES = ("system_prompt.md", "system_prompt.txt")
_DB_FILES = ("agent.db",)
_LETTA_MARKER = ".letta"

_BLOCK_LABEL_MAP: dict[str, MemoryLabel] = {
    "persona": MemoryLabel.PERSONA,
    "human": MemoryLabel.CONTEXT,
    "system": MemoryLabel.FLOW,
}

FILE_PATTERNS = [
    "*.json", "*.md", "*.txt", "*.yaml", "*.yml", "*.af",
    "tools/*.py", "archival/*.txt", "archival/*.md", "archival/*.json",
    ".letta/*.json",
]
"""Glob patterns the pipeline uses to read source files from disk."""


class LettaSpawner:
    """Parse a Letta agent export directory, database, or AgentFile."""

    FILE_PATTERNS = FILE_PATTERNS

    def detect(self, input_path: Path) -> bool:
        """Return True if input_path looks like a Letta project."""
        if input_path.is_file():
            if input_path.suffix == ".db":
                return self._is_letta_db(input_path)
            if input_path.suffix == ".af":
                return self._is_agent_file(input_path)

        if not input_path.is_dir():
            return False

        if (input_path / _LETTA_MARKER).is_dir():
            return True
        if any((input_path / f).exists() for f in _AGENT_STATE_FILES):
            return True
        if any((input_path / f).exists() for f in _DB_FILES):
            return True
        if list(input_path.glob("*.af")):
            return True

        tools_dir = input_path / "tools"
        if tools_dir.is_dir() and list(tools_dir.glob("*.py")):
            return True

        return False

    def parse(self, files: dict[str, str]) -> ParseResult:
        """Parse pre-redacted file contents into raw skills and memory.

        Parameters
        ----------
        files:
            Mapping of ``filename -> UTF-8 content`` (already redacted).
            For DB-mode, the pipeline stores table data as ``_db_tables.json``
            and other synthetic keys.

        Returns
        -------
        ParseResult
            Skills, memory, and MCP configs extracted from the files.
        """
        af_result = self._try_parse_agent_file(files)
        if af_result is not None:
            return af_result

        skills = self._parse_skills(files)
        memories = self._parse_memories(files)
        mcp_configs = self._parse_mcp_configs(files)
        return ParseResult(
            skills=skills, memory=memories, mcp_configs=mcp_configs,
        )

    def parse_db(self, db_path: Path, supplemental_files: dict[str, str] | None = None) -> ParseResult:
        """Parse directly from a Letta SQLite database.

        This is the special case for DB-mode extraction. The pipeline calls
        this instead of ``parse()`` when the source is a ``.db`` file.
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
                        memories.append(RawMemory(
                            text=text.strip(), source_file=f"db.blocks.{label_key}", label=label,
                        ))
            if "archival_memory" in tables:
                for row in conn.execute("SELECT * FROM archival_memory ORDER BY rowid").fetchall():
                    text = dict(row).get("text", "")
                    if text and isinstance(text, str):
                        memories.append(RawMemory(
                            text=text.strip(), source_file="db.archival_memory", label=MemoryLabel.STATE,
                        ))
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

    def validate(self, input_path: Path) -> ValidationReport:
        """Validate a Letta source before spawning."""
        issues: list[ValidationIssue] = []

        if input_path.is_file():
            if input_path.suffix == ".db":
                if not self._is_letta_db(input_path):
                    issues.append(
                        ValidationIssue(
                            level="error",
                            message=f"Not a valid Letta database: {input_path}",
                            location=str(input_path),
                        )
                    )
                return ValidationReport(
                    valid=not any(i.level == "error" for i in issues), issues=issues
                )
            if input_path.suffix == ".af":
                if not self._is_agent_file(input_path):
                    issues.append(
                        ValidationIssue(
                            level="error",
                            message=f"Not a valid Letta AgentFile: {input_path}",
                            location=str(input_path),
                        )
                    )
                return ValidationReport(
                    valid=not any(i.level == "error" for i in issues), issues=issues
                )
            issues.append(
                ValidationIssue(
                    level="error",
                    message=f"Not a directory, .db, or .af file: {input_path}",
                    location=str(input_path),
                )
            )
            return ValidationReport(valid=False, issues=issues)

        if not input_path.is_dir():
            issues.append(
                ValidationIssue(
                    level="error",
                    message=f"Not a directory, .db, or .af file: {input_path}",
                    location=str(input_path),
                )
            )
            return ValidationReport(valid=False, issues=issues)

        has_state = any((input_path / f).exists() for f in _AGENT_STATE_FILES)
        has_db = any((input_path / f).exists() for f in _DB_FILES)
        has_marker = (input_path / _LETTA_MARKER).is_dir()
        has_tools = (input_path / "tools").is_dir()
        has_af = bool(list(input_path.glob("*.af")))

        if not has_state and not has_db and not has_marker and not has_tools and not has_af:
            issues.append(
                ValidationIssue(
                    level="warning",
                    message=(
                        "No agent_state.json, agent.db, .af, .letta/ marker, or tools/ "
                        "found, Egg will be sparse"
                    ),
                    location=str(input_path),
                )
            )

        if has_state:
            state_path = input_path / "agent_state.json"
            try:
                data = json.loads(state_path.read_text())
                if not isinstance(data, dict):
                    issues.append(
                        ValidationIssue(
                            level="error",
                            message="agent_state.json must be a JSON object",
                            location=str(state_path),
                        )
                    )
            except json.JSONDecodeError as exc:
                issues.append(
                    ValidationIssue(
                        level="error",
                        message=f"Invalid JSON in agent_state.json: {exc}",
                        location=str(state_path),
                    )
                )

        return ValidationReport(
            valid=not any(i.level == "error" for i in issues), issues=issues
        )

    # ------------------------------------------------------------------
    # AgentFile (.af) parsing
    # ------------------------------------------------------------------

    def _try_parse_agent_file(self, files: dict[str, str]) -> ParseResult | None:
        """Try to parse a .af AgentFile from the files dict. Returns None if no .af found."""
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

        skills: list[RawSkill] = []
        memories: list[RawMemory] = []
        mcp_configs: dict[str, dict] = {}
        source_metadata: dict[str, str] = {}

        self._parse_af_memory_blocks(data, memories, af_name)
        self._parse_af_system_prompt(data, memories, af_name)
        self._parse_af_tools(data, skills, af_name)
        self._parse_af_tool_rules(data, memories, af_name)
        self._parse_af_messages(data, memories, af_name)
        self._parse_af_env_vars(data, memories, af_name)
        self._parse_af_mcp_servers(data, mcp_configs)
        self._parse_af_model_config(data, source_metadata)

        dir_skills = self._parse_skills(files)
        seen_names = {s.name for s in skills}
        for s in dir_skills:
            if s.name not in seen_names:
                skills.append(s)

        dir_mcp = self._parse_mcp_configs(files)
        for k, v in dir_mcp.items():
            if k not in mcp_configs:
                mcp_configs[k] = v

        return ParseResult(
            skills=skills, memory=memories,
            mcp_configs=mcp_configs, source_metadata=source_metadata,
        )

    @staticmethod
    def _parse_af_memory_blocks(data: dict, memories: list[RawMemory], af_name: str | None) -> None:
        blocks = data.get("memory", data.get("blocks", {}))
        if isinstance(blocks, dict):
            for block_name, block_value in blocks.items():
                text = _extract_block_text(block_value)
                if text:
                    label = _BLOCK_LABEL_MAP.get(block_name, MemoryLabel.CONTEXT)
                    memories.append(RawMemory(
                        text=text,
                        source_file=f"{af_name}#memory.{block_name}",
                        label=label,
                    ))
        elif isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                name = block.get("label", block.get("name", ""))
                text = _extract_block_text(block)
                if text:
                    label = _BLOCK_LABEL_MAP.get(name, MemoryLabel.CONTEXT)
                    memories.append(RawMemory(
                        text=text,
                        source_file=f"{af_name}#blocks.{name}",
                        label=label,
                    ))

    @staticmethod
    def _parse_af_system_prompt(data: dict, memories: list[RawMemory], af_name: str | None) -> None:
        system = data.get("system", data.get("system_prompt", ""))
        if system and isinstance(system, str):
            memories.append(RawMemory(
                text=system.strip(),
                source_file=f"{af_name}#system",
                label=MemoryLabel.FLOW,
            ))

    @staticmethod
    def _parse_af_tools(data: dict, skills: list[RawSkill], af_name: str | None) -> None:
        tools = data.get("tools", [])
        if not isinstance(tools, list):
            return
        for tool_def in tools:
            if not isinstance(tool_def, dict):
                continue
            tname = tool_def.get("name", "")
            tsource = tool_def.get("source_code", "")
            if tsource:
                skills.append(RawSkill(
                    name=_python_module_display_name(tname) if tname else "unnamed_tool",
                    content=tsource,
                    source_file=af_name or ".af",
                ))

    @staticmethod
    def _parse_af_tool_rules(data: dict, memories: list[RawMemory], af_name: str | None) -> None:
        """Parse tool_rules as FLOW memory (behavioral sequencing constraints)."""
        rules = data.get("tool_rules", [])
        if not isinstance(rules, list) or not rules:
            return
        rule_texts = []
        for rule in rules:
            if isinstance(rule, dict):
                rule_texts.append(json.dumps(rule))
            elif isinstance(rule, str):
                rule_texts.append(rule)
        if rule_texts:
            memories.append(RawMemory(
                text="\n".join(rule_texts),
                source_file=f"{af_name}#tool_rules",
                label=MemoryLabel.FLOW,
            ))

    @staticmethod
    def _parse_af_messages(data: dict, memories: list[RawMemory], af_name: str | None) -> None:
        """Parse message history as STATE memory."""
        messages = data.get("messages", [])
        if not isinstance(messages, list):
            return
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            text = msg.get("text", msg.get("content", ""))
            if not text or not isinstance(text, str):
                continue
            role = msg.get("role", "")
            ts = _parse_timestamp(msg.get("created_at", msg.get("timestamp")))
            memories.append(RawMemory(
                text=text.strip(),
                source_file=f"{af_name}#messages.{role}",
                label=MemoryLabel.STATE,
                timestamp=ts,
            ))

    @staticmethod
    def _parse_af_env_vars(data: dict, memories: list[RawMemory], af_name: str | None) -> None:
        """Parse env_vars. After redaction these become SECRET placeholders.

        We store them as CONTEXT memory so the credential scanner
        (which runs before parsing) can replace the raw values with
        {{SECRET_NNN}} placeholders.  The pipeline's secret builder
        will then promote them to SecretRecords.
        """
        env_vars = data.get("env_vars", data.get("environment_variables", {}))
        if not isinstance(env_vars, dict) or not env_vars:
            return
        lines = [f"{k}={v}" for k, v in env_vars.items() if isinstance(v, str)]
        if lines:
            memories.append(RawMemory(
                text="\n".join(lines),
                source_file=f"{af_name}#env_vars",
                label=MemoryLabel.CONTEXT,
            ))

    @staticmethod
    def _parse_af_mcp_servers(data: dict, mcp_configs: dict[str, dict]) -> None:
        servers = data.get("mcp_servers", [])
        if not isinstance(servers, list):
            return
        for srv in servers:
            if not isinstance(srv, dict):
                continue
            name = srv.get("name", srv.get("server_name", ""))
            if name:
                mcp_configs[name] = srv

    @staticmethod
    def _parse_af_model_config(data: dict, source_metadata: dict[str, str]) -> None:
        for key in ("model", "model_name", "embedding_model", "context_window"):
            val = data.get(key)
            if val is not None:
                source_metadata[f"letta.{key}"] = str(val)
        llm = data.get("llm_config", data.get("model_config", {}))
        if isinstance(llm, dict):
            for key in ("model", "model_endpoint", "context_window"):
                val = llm.get(key)
                if val is not None:
                    source_metadata[f"letta.llm.{key}"] = str(val)

    # ------------------------------------------------------------------
    # Parse helpers (operate on file dict, not filesystem)
    # ------------------------------------------------------------------

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
                memories.append(RawMemory(
                    text=system_text.strip(), source_file="agent_state.json",
                    label=MemoryLabel.FLOW,
                ))
                has_system = True
            mem_blocks = state.get("memory", {})
            if isinstance(mem_blocks, dict):
                for block_name, block_value in mem_blocks.items():
                    text = _extract_block_text(block_value)
                    if text:
                        label = _BLOCK_LABEL_MAP.get(block_name, MemoryLabel.CONTEXT)
                        memories.append(RawMemory(
                            text=text,
                            source_file=f"agent_state.json#memory.{block_name}",
                            label=label,
                        ))

        if not has_system:
            for fname in _SYSTEM_PROMPT_FILES:
                content = files.get(fname, "").strip()
                if content:
                    memories.append(RawMemory(
                        text=content, source_file=fname, label=MemoryLabel.FLOW,
                    ))
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
                    memories.append(RawMemory(
                        text=text, source_file=fname, label=MemoryLabel.STATE, timestamp=ts,
                    ))

        for key, content in sorted(files.items()):
            if not key.startswith("archival/"):
                continue
            if key.endswith((".txt", ".md")):
                text = content.strip()
                if text:
                    memories.append(RawMemory(
                        text=text, source_file=key, label=MemoryLabel.STATE,
                    ))
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
                            memories.append(RawMemory(
                                text=text, source_file=key, label=MemoryLabel.STATE,
                            ))

        return memories

    @staticmethod
    def _parse_mcp_configs(files: dict[str, str]) -> dict[str, dict]:
        return _parse_mcp_configs_from_files(files)

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _find_db(self, root: Path) -> Path | None:
        """Find a Letta SQLite database in the project directory."""
        for fname in _DB_FILES:
            fpath = root / fname
            if fpath.exists():
                return fpath
        return None

    def _is_letta_db(self, db_path: Path) -> bool:
        """Check if a file is a valid Letta SQLite database."""
        if not db_path.exists() or not db_path.is_file():
            return False
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()
            return "agents" in tables or "blocks" in tables
        except (sqlite3.Error, OSError):
            return False

    @staticmethod
    def _is_agent_file(af_path: Path) -> bool:
        """Check if a file is a valid Letta AgentFile."""
        if not af_path.exists() or not af_path.is_file():
            return False
        try:
            data = json.loads(af_path.read_text())
            return isinstance(data, dict) and (
                "memory" in data or "blocks" in data
                or "tools" in data or "system" in data
            )
        except (json.JSONDecodeError, OSError):
            return False

    @staticmethod
    def _get_tables(conn: sqlite3.Connection) -> set[str]:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
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
        return (
            block_value.get("value", "")
            or block_value.get("text", "")
        ).strip()
    return ""


def _python_module_display_name(stem: str) -> str:
    """Convert a Python module name to a display name (e.g., search_web -> search web)."""
    return stem.replace("_", " ").replace("-", " ").strip()
