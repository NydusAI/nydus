"""Shared utilities for source spawners and target hatchers.

Helpers for paragraph splitting, MCP config discovery, skill filenames, and
lightweight parsing used by OpenClaw, ZeroClaw, and Letta connectors.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pynydus.api.schemas import MemoryRecord


def split_paragraphs(text: str) -> list[str]:
    """Split text into non-empty paragraphs.

    Paragraphs are separated by one or more blank lines.

    Args:
        text: Full document text.

    Returns:
        Non-empty paragraph strings in order.
    """
    paragraphs: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append("\n".join(current))
            current = []
    if current:
        paragraphs.append("\n".join(current))
    return paragraphs


def parse_mcp_configs_from_files(files: dict[str, str]) -> dict[str, dict]:
    """Parse MCP server configurations from a virtual file tree.

    Loads ``mcp.json`` (mapping of server name to config), then applies each
    ``mcp/<name>.json`` file. A per-file entry replaces an existing same-named
    server from ``mcp.json``.

    Args:
        files: Map of relative path to file body (e.g. from a spawn snapshot).

    Returns:
        Mapping of server name to configuration dict.
    """
    configs: dict[str, dict] = {}

    mcp_json = files.get("mcp.json", "")
    if mcp_json:
        try:
            data = json.loads(mcp_json)
            if isinstance(data, dict):
                servers = data.get("mcpServers", data)
                for name, cfg in servers.items():
                    if isinstance(cfg, dict):
                        configs[name] = cfg
        except json.JSONDecodeError:
            pass

    for key, content in sorted(files.items()):
        if key.startswith("mcp/") and key.endswith(".json"):
            try:
                cfg = json.loads(content)
                if isinstance(cfg, dict):
                    stem = key.removeprefix("mcp/").removesuffix(".json")
                    configs[stem] = cfg
            except json.JSONDecodeError:
                pass

    return configs


def skill_to_filename(name: str) -> str:
    """Turn a skill display name into a safe ``.py`` module filename.

    Args:
        name: Human-readable skill name.

    Returns:
        Filename such as ``my_skill.py``, prefixed with ``tool_`` if the stem
        would otherwise start with a digit. Falls back to ``tool.py`` if empty
        after normalization.
    """
    module = name.lower().strip().replace(" ", "_").replace("-", "_")
    module = "".join(c for c in module if c.isalnum() or c == "_")
    if module and module[0].isdigit():
        module = f"tool_{module}"
    if not module:
        module = "tool"
    return f"{module}.py"


def parse_timestamp(val: object) -> datetime | None:
    """Parse a timestamp from common string or numeric forms.

    Args:
        val: ISO-like string, Unix epoch seconds, or ``None``.

    Returns:
        Aware or naive :class:`~datetime.datetime` on success. ``None`` if
        *val* is ``None`` or cannot be parsed.
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val, tz=UTC)
        except (ValueError, OSError):
            return None
    if isinstance(val, str):
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
    return None


_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def extract_date_from_filename(name: str) -> datetime | None:
    """Extract a YYYY-MM-DD date from a filename like ``memory/2026-03-15.md``."""
    m = _DATE_RE.search(name)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def date_key_from_record(rec: MemoryRecord) -> str | None:
    """Extract a YYYY-MM-DD date key from a state record.

    Prefers the record's timestamp field. Falls back to extracting a date
    from source_store (e.g. ``memory/2026-04-01.md``).
    """
    if rec.timestamp:
        return rec.timestamp.strftime("%Y-%m-%d")
    m = re.search(r"(\d{4}-\d{2}-\d{2})", rec.source_store)
    if m:
        return m.group(1)
    return None


def join_records(records: list[MemoryRecord]) -> str:
    """Join memory records into a single file's content."""
    return "\n\n".join(r.text for r in records) + "\n"
