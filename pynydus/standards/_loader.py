"""Spec file loader and shared validation helper.

Each spec file lives in ``specs/<name>.md`` and optionally contains a
JSON Schema block delimited by ``<!-- nydus:schema ... -->`` markers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema

from pynydus.api.schemas import ValidationIssue

_SPECS_DIR = Path(__file__).resolve().parent.parent.parent / "specs"

_SCHEMA_BLOCK_RE = re.compile(
    r"<!--\s*nydus:schema\s+\w+\s*-->\s*\n"
    r"```json\s*\n"
    r"(.*?)"
    r"\n```\s*\n"
    r"<!--\s*/nydus:schema\s*-->",
    re.DOTALL,
)


def load_spec(name: str) -> tuple[str, dict[str, Any] | None]:
    """Load a spec markdown file and extract its embedded JSON Schema.

    Args:
        name: Standard name (e.g. ``"mcp"``, ``"agentskills"``, ``"a2a"``).
              Maps to ``specs/<name>.md``.

    Returns:
        ``(full_markdown_text, json_schema_dict_or_None)``.
        The schema is ``None`` when the spec has no embedded schema block
        (e.g. ``apm.md``).

    Raises:
        FileNotFoundError: If the spec file does not exist.
        json.JSONDecodeError: If the schema block is not valid JSON.
    """
    path = _SPECS_DIR / f"{name}.md"
    md = path.read_text(encoding="utf-8")
    schema = _extract_schema_block(md)
    return md, schema


def validate_against_schema(
    instance: Any,
    spec_name: str,
    *,
    schema: dict[str, Any] | None = None,
    level: str = "warning",
    label: str = "",
    location: str = "",
) -> list[ValidationIssue]:
    """Validate *instance* against a spec's embedded JSON Schema.

    Args:
        instance: JSON-compatible object to validate.
        spec_name: Standard name to load schema from (e.g. ``"mcp"``).
        schema: Override schema. If ``None``, loads from the spec file.
        level: Issue level for findings (``"warning"`` or ``"error"``).
        label: Prefix for the issue message (e.g. ``"MCP schema"``).
        location: Base location string for the issue.

    Returns:
        List of :class:`ValidationIssue` (empty when valid).
    """
    if schema is None:
        _, schema = load_spec(spec_name)
    if schema is None:
        return []

    issues: list[ValidationIssue] = []
    validator = jsonschema.Draft202012Validator(schema)
    for error in validator.iter_errors(instance):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        loc = f"{location}:{path}" if location else path
        msg = f"{label}: {error.message}" if label else error.message
        issues.append(ValidationIssue(level=level, message=msg, location=loc))
    return issues


def _extract_schema_block(md: str) -> dict[str, Any] | None:
    """Extract the first ``<!-- nydus:schema ... -->`` JSON Schema block.

    Returns:
        Parsed JSON Schema dict, or ``None`` if no block is found.
    """
    m = _SCHEMA_BLOCK_RE.search(md)
    if not m:
        return None
    return json.loads(m.group(1))
