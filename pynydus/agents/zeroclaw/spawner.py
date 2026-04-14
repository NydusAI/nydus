"""ZeroClaw spawner connector. Spec §11.6.

Parses a ZeroClaw workspace directory containing:
- SOUL.md / persona.md    -> memory records labeled "persona"
- IDENTITY.md             -> memory records labeled "persona"
- identity.json           -> memory records labeled "persona" (AIEOS format)
- AGENTS.md / instructions.md / system_prompt.md -> memory records labeled "flow"
- HEARTBEAT.md            -> memory records labeled "flow"
- USER.md / context.md    -> memory records labeled "context"
- TOOLS.md                -> memory records labeled "context"
- MEMORY.md               -> memory records labeled "state"
- memory/YYYY-MM-DD.md    -> memory records labeled "state"
- memory/session_*.md     -> memory records labeled "state"
- memory.db (SQLite)      -> memory records by category (Core/Daily/Conversation)
- tools/                  -> Python tool files -> skill records
- tools.json              -> tool manifest with metadata
- .zeroclaw/              -> marker directory (optional)
- config.json / config.yaml / config.toml -> secret requirements
"""

from __future__ import annotations

import json
import sqlite3
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]
from datetime import datetime, timezone
from pathlib import Path

from pynydus.api.errors import ConnectorError
from pynydus.api.protocols import Spawner
from pynydus.api.raw_types import (
    ParseResult,
    RawMemory,
    RawSkill,
)
from pynydus.common.connector_utils import (
    extract_date_from_filename as _extract_date_from_filename,
)
from pynydus.common.connector_utils import (
    parse_mcp_configs_from_files as _parse_mcp_configs_from_files,
)
from pynydus.common.connector_utils import (
    split_paragraphs as _split_paragraphs,
)
from pynydus.common.enums import MemoryLabel

_PERSONA_FILES = ("SOUL.md", "persona.md", "IDENTITY.md")
_FLOW_FILES = ("AGENTS.md", "agents.md", "instructions.md", "system_prompt.md", "HEARTBEAT.md")
_CONTEXT_FILES = ("USER.md", "user.md", "context.md", "TOOLS.md")
_STATE_FILES = ("MEMORY.md", "knowledge.md")
_CONFIG_FILES = ("config.json", "config.yaml", "config.yml", "config.toml")

_CATEGORY_LABEL_MAP: dict[str, MemoryLabel] = {
    "core": MemoryLabel.STATE,
    "daily": MemoryLabel.STATE,
    "conversation": MemoryLabel.STATE,
}

FILE_PATTERNS = [
    "*.md",
    "*.yaml",
    "*.yml",
    "*.json",
    "*.txt",
    "*.toml",
    "tools/*.py",
    "memory/*.md",
]
"""Glob patterns the pipeline uses to read source files from disk."""


class ZeroClawSpawner(Spawner):
    """Parse a ZeroClaw project directory."""

    FILE_PATTERNS = FILE_PATTERNS

    def parse(self, files: dict[str, str]) -> ParseResult:
        """Parse pre-redacted file contents into raw skills and memory.

        Args:
            files: ``filename -> UTF-8 content`` (already redacted).

        Returns:
            Skills, memory, MCP configs, and neutral metadata when present in config.
        """
        skills = self._parse_skills(files)
        memories = self._parse_memories(files)
        mcp_configs = self._parse_mcp_configs(files)
        agent_name, agent_description, llm_model = _parse_neutral_metadata_from_toml(files)
        return ParseResult(
            skills=skills,
            memory=memories,
            mcp_configs=mcp_configs,
            agent_name=agent_name,
            agent_description=agent_description,
            llm_model=llm_model,
        )

    def parse_db(
        self, db_path: Path, supplemental_files: dict[str, str] | None = None
    ) -> ParseResult:
        """Parse memory entries from a ZeroClaw memory.db SQLite database.

        ZeroClaw stores MemoryEntry records with category fields
        (Core, Daily, Conversation, Custom).

        Args:
            db_path: Path to the ``memory.db`` SQLite file.
            supplemental_files: Additional text files to parse alongside the DB.

        Returns:
            Skills, memory, MCP configs, and neutral metadata from supplemental files.
        """
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            raise ConnectorError(f"Cannot open ZeroClaw memory database: {exc}") from exc

        memories: list[RawMemory] = []

        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

            memory_table = None
            for candidate in ("memory_entries", "memories", "memory"):
                if candidate in tables:
                    memory_table = candidate
                    break

            if memory_table:
                for row in conn.execute(f"SELECT * FROM {memory_table} ORDER BY rowid").fetchall():
                    row_dict = dict(row)
                    text = row_dict.get("content", row_dict.get("text", row_dict.get("value", "")))
                    if not text or not isinstance(text, str):
                        continue
                    category = str(row_dict.get("category", row_dict.get("type", ""))).lower()
                    label = _CATEGORY_LABEL_MAP.get(category, MemoryLabel.STATE)
                    ts = _extract_timestamp_from_row(row_dict)
                    memories.append(
                        RawMemory(
                            text=text.strip(),
                            source_file=f"memory.db.{category or 'unknown'}",
                            label=label,
                            timestamp=ts,
                        )
                    )
        finally:
            conn.close()

        result = ParseResult(memory=memories)
        if supplemental_files:
            supp = self.parse(supplemental_files)
            result.skills = supp.skills
            result.memory.extend(supp.memory)
            result.mcp_configs = supp.mcp_configs
            if supp.agent_name:
                result.agent_name = supp.agent_name
            if supp.agent_description:
                result.agent_description = supp.agent_description
            if supp.llm_model:
                result.llm_model = supp.llm_model

        return result

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
                            name=stem.replace("_", " "),
                            content=content,
                            source_file=key,
                        )
                    )

        tools_json = files.get("tools.json", "")
        if tools_json and not skills:
            try:
                data = json.loads(tools_json)
                if isinstance(data, list):
                    for entry in data:
                        if isinstance(entry, dict) and "name" in entry:
                            skills.append(
                                RawSkill(
                                    name=entry["name"],
                                    content=entry.get("source", entry.get("description", "")),
                                    source_file="tools.json",
                                )
                            )
            except json.JSONDecodeError:
                pass

        return skills

    def _parse_memories(self, files: dict[str, str]) -> list[RawMemory]:
        """Parse memory from all recognized ZeroClaw workspace files."""
        memories: list[RawMemory] = []

        file_label_map = [
            (_PERSONA_FILES, MemoryLabel.PERSONA),
            (_FLOW_FILES, MemoryLabel.FLOW),
            (_CONTEXT_FILES, MemoryLabel.CONTEXT),
            (_STATE_FILES, MemoryLabel.STATE),
        ]

        for filenames, label in file_label_map:
            for fname in filenames:
                content = files.get(fname, "").strip()
                if not content:
                    continue
                for para in _split_paragraphs(content):
                    memories.append(RawMemory(text=para, source_file=fname, label=label))

        identity = files.get("identity.json", "")
        if identity:
            try:
                data = json.loads(identity)
                if isinstance(data, dict):
                    text_parts = []
                    for field in (
                        "name",
                        "description",
                        "personality",
                        "vibe",
                        "backstory",
                        "role",
                    ):
                        val = data.get(field)
                        if val and isinstance(val, str):
                            text_parts.append(val.strip())
                    if text_parts:
                        memories.append(
                            RawMemory(
                                text="\n\n".join(text_parts),
                                source_file="identity.json",
                                label=MemoryLabel.PERSONA,
                            )
                        )
            except json.JSONDecodeError:
                pass

        for key, content in sorted(files.items()):
            if not key.startswith("memory/") or not key.endswith(".md"):
                continue
            content = content.strip()
            if not content:
                continue
            ts = _extract_date_from_filename(key)
            for para in _split_paragraphs(content):
                memories.append(
                    RawMemory(text=para, source_file=key, label=MemoryLabel.STATE, timestamp=ts)
                )

        return memories

    @staticmethod
    def _parse_mcp_configs(files: dict[str, str]) -> dict[str, dict]:
        return _parse_mcp_configs_from_files(files)


def _parse_neutral_metadata_from_toml(
    files: dict[str, str],
) -> tuple[str | None, str | None, str | None]:
    """Map config.toml fields into neutral ParseResult metadata."""
    toml_content = files.get("config.toml", "")
    if not toml_content or tomllib is None:
        return None, None, None
    try:
        data = tomllib.loads(toml_content)
    except (ValueError, KeyError):
        return None, None, None
    agent_name = None
    agent_description = None
    llm_model = None
    top_name = data.get("name")
    if isinstance(top_name, str) and top_name:
        agent_name = top_name
    top_desc = data.get("description")
    if isinstance(top_desc, str) and top_desc:
        agent_description = top_desc
    top_model = data.get("model")
    if isinstance(top_model, str) and top_model:
        llm_model = top_model
    agent = data.get("agent", {})
    if isinstance(agent, dict):
        an = agent.get("name")
        if isinstance(an, str) and an:
            agent_name = an
        am = agent.get("model")
        if isinstance(am, str) and am:
            llm_model = am
    return agent_name, agent_description, llm_model


def _extract_timestamp_from_row(row: dict) -> datetime | None:
    """Try to extract a timestamp from a database row."""
    for field in ("created_at", "timestamp", "date"):
        val = row.get(field)
        if not val:
            continue
        if isinstance(val, (int, float)):
            try:
                return datetime.fromtimestamp(val, tz=timezone.utc)
            except (OSError, ValueError):
                continue
        if isinstance(val, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(val.rstrip("Z"), fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    return None
