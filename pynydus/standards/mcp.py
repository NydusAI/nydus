"""MCP standard: validate, extract, generate.

Follows the Claude Desktop de facto convention for ``mcp.json``.
"""

from __future__ import annotations

import json
from typing import Any

from pynydus.api.schemas import Egg, ValidationIssue
from pynydus.standards._loader import validate_against_schema


def validate(egg: Egg, schema: dict[str, Any] | None = None) -> list[ValidationIssue]:
    """Validate the egg's MCP configs against the spec schema."""
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

    Returns:
        ``{"mcp.json": <content>}`` or empty dict if no MCP configs.
    """
    if not egg.mcp.configs:
        return {}

    doc = {"mcpServers": egg.mcp.configs}
    return {"mcp.json": json.dumps(doc, indent=2) + "\n"}


def generate(egg: Egg) -> dict[str, str]:
    """Generate MCP config from egg data.

    For MCP this is the same as extract — configs are stored verbatim
    and there is no generation step. Provided for interface consistency.
    """
    return extract(egg)
