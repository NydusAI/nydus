"""Shared utilities for source spawners and target hatchers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Regex for secret-like keys in config files (used by multiple spawners)
# ---------------------------------------------------------------------------

SECRET_PATTERN = re.compile(
    r"""(?:api[_-]?key|secret|token|password|credential|auth)"""
    r"""\s*[:=]\s*["']?(\S+?)["']?\s*$""",
    re.IGNORECASE | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def split_paragraphs(text: str) -> list[str]:
    """Split text into non-empty paragraphs (separated by blank lines)."""
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


def extract_key_name(line: str) -> str:
    """Extract the key name from a ``key: value`` or ``key=value`` line."""
    return re.split(r"\s*[:=]\s*", line.strip())[0].strip().strip('"').strip("'")


def parse_mcp_configs_from_files(files: dict[str, str]) -> dict[str, dict]:
    """Parse MCP server configurations from a file dict.

    Looks for ``mcp.json`` (multi-server object) and ``mcp/<name>.json``
    (one server per file) entries in the file dict.
    """
    configs: dict[str, dict] = {}

    mcp_json = files.get("mcp.json", "")
    if mcp_json:
        try:
            data = json.loads(mcp_json)
            if isinstance(data, dict):
                for name, cfg in data.items():
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
    """Convert a skill display name to a Python filename."""
    module = name.lower().strip().replace(" ", "_").replace("-", "_")
    module = "".join(c for c in module if c.isalnum() or c == "_")
    if module and module[0].isdigit():
        module = f"tool_{module}"
    if not module:
        module = "tool"
    return f"{module}.py"


def looks_like_placeholder(val: str) -> bool:
    """Check if a value is already a placeholder token."""
    return bool(re.match(r"\{\{(SECRET|PII)_\d+\}\}", val))


def parse_timestamp(val: object) -> datetime | None:
    """Best-effort parse a timestamp string or number."""
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
