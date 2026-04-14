"""OpenClaw spawner connector. Spec §10.3.

Parses an OpenClaw workspace directory containing:
- SOUL.md / soul.md       -> memory records labeled "persona"
- IDENTITY.md             -> memory records labeled "persona"
- AGENTS.md               -> memory records labeled "flow"
- BOOT.md / HEARTBEAT.md  -> memory records labeled "flow"
- USER.md                 -> memory records labeled "context"
- TOOLS.md                -> memory records labeled "context"
- knowledge.md / MEMORY.md -> memory records labeled "state"
- memory/YYYY-MM-DD.md    -> memory records labeled "state"
- skill.md / skills.md / skills/ -> skill records
- config.yaml / config.json -> secret requirements
"""

from __future__ import annotations

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

_PERSONA_FILES = ("SOUL.md", "soul.md", "IDENTITY.md")
_FLOW_FILES = ("AGENTS.md", "agents.md", "BOOT.md", "HEARTBEAT.md")
_CONTEXT_FILES = ("USER.md", "user.md", "TOOLS.md")
_STATE_FILES = ("knowledge.md", "MEMORY.md")
_SKILL_FILES = ("skill.md", "skills.md")

FILE_PATTERNS = ["*.md", "*.yaml", "*.yml", "*.json", "*.txt", "skills/*.md", "memory/*.md"]
"""Glob patterns the pipeline uses to read source files from disk."""


class OpenClawSpawner(Spawner):
    """Parse OpenClaw workspace directory."""

    FILE_PATTERNS = FILE_PATTERNS

    def parse(self, files: dict[str, str]) -> ParseResult:
        """Parse pre-redacted file contents into raw skills and memory.

        Args:
            files: ``filename -> UTF-8 content`` (already redacted).

        Returns:
            Skills, memory, and MCP configs.
        """
        skills = self._parse_skills(files)
        memories = self._parse_memories(files)
        mcp_configs = self._parse_mcp_configs(files)
        return ParseResult(skills=skills, memory=memories, mcp_configs=mcp_configs)

    # ---------------------------------------------------------------------------
    # Parse helpers (operate on file dict, not filesystem)
    # ---------------------------------------------------------------------------

    def _parse_skills(self, files: dict[str, str]) -> list[RawSkill]:
        """Parse skills from file contents dict."""
        skills: list[RawSkill] = []
        for fname in _SKILL_FILES:
            content = files.get(fname, "")
            if content:
                for block in _split_markdown_sections(content):
                    skills.append(
                        RawSkill(name=block["name"], content=block["content"], source_file=fname)
                    )
        for key, content in sorted(files.items()):
            if key.startswith("skills/") and key.endswith(".md"):
                content = content.strip()
                if content:
                    stem = key.removeprefix("skills/").removesuffix(".md")
                    skills.append(
                        RawSkill(
                            name=stem.replace("_", " ").replace("-", " "),
                            content=content,
                            source_file=key,
                        )
                    )
        return skills

    def _parse_memories(self, files: dict[str, str]) -> list[RawMemory]:
        """Parse memory from all recognized OpenClaw workspace files."""
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


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _split_markdown_sections(text: str) -> list[dict[str, str]]:
    """Split markdown into sections by headings. Returns [{name, content}]."""
    sections: list[dict[str, str]] = []
    current_name = "default"
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("#"):
            if current_lines:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append({"name": current_name, "content": content})
                current_lines = []
            current_name = line.lstrip("#").strip()
        else:
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append({"name": current_name, "content": content})

    if not sections and text.strip():
        sections.append({"name": "default", "content": text.strip()})

    return sections
