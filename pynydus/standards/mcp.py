"""MCP standard: validate, extract, generate.

Follows the Claude Desktop de facto convention for ``mcp.json``.
"""

from __future__ import annotations

import json
from typing import Any

from pynydus.api.schemas import Egg, ValidationIssue
from pynydus.standards._loader import validate_against_schema


def validate(egg: Egg, schema: dict[str, Any] | None = None) -> list[ValidationIssue]:
    """Validate the egg's MCP configs against the spec schema.

    Args:
        egg: The Egg to validate.
        schema: Optional JSON Schema dict. When ``None``, the schema is loaded
            from the bundled ``mcp`` spec.

    Returns:
        List of validation issues (empty if valid or if there are no MCP configs).
    """
    if not egg.mcp.configs:
        return []

    return validate_against_schema(
        {"mcpServers": egg.mcp.configs},
        "mcp",
        schema=schema,
        label="MCP schema",
        location="mcp.json",
    )


def extract(egg: Egg) -> dict[str, str]:
    """Extract MCP config from the egg.

    Args:
        egg: The Egg containing MCP server configs.

    Returns:
        ``{"mcp.json": <content>}`` or empty dict if no MCP configs.
    """
    if not egg.mcp.configs:
        return {}

    doc = {"mcpServers": egg.mcp.configs}
    return {"mcp.json": json.dumps(doc, indent=2) + "\n"}


def generate(egg: Egg) -> dict[str, str]:
    """Generate MCP config from egg data.

    For MCP this is the same as extract. Configs are stored verbatim
    and there is no generation step. Provided for interface consistency.

    Args:
        egg: The Egg containing MCP server configs.

    Returns:
        Same as :func:`extract`: ``{"mcp.json": <content>}`` or empty dict.
    """
    return extract(egg)
