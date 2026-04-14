"""Standards validation, extraction, and generation.

Each sub-module corresponds to one agentic standard (MCP, Agent Skills,
A2A, APM, AGENTS.md) and exposes up to three functions:

    validate(egg, schema=None) -> list[ValidationIssue]
    extract(egg) -> dict[str, str]
    generate(egg, **kwargs) -> dict[str, str]

Not all modules implement all three. APM only has ``extract()``.
"""

from pynydus.standards._loader import load_spec, validate_against_schema

__all__ = ["load_spec", "validate_against_schema"]
