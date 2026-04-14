"""AGENTS.md standard: validate, extract, generate.

Generates a per-egg deployment runbook from egg data.
"""

from __future__ import annotations

import re
from typing import Any

from pynydus.api.schemas import Egg, ValidationIssue
from pynydus.standards._loader import validate_against_schema


def validate(egg: Egg, schema: dict[str, Any] | None = None) -> list[ValidationIssue]:
    """Validate the egg's per-egg AGENTS.md structural completeness.

    Checks that required sections (Prerequisites, Hatch) are present,
    and that optional sections exist when the egg has relevant data.
    """
    if egg.agents_md is None:
        return []

    doc = _parse_sections(egg.agents_md)
    return validate_against_schema(
        doc,
        "agents",
        schema=schema,
        label="AGENTS.md",
        location="AGENTS.md",
    )


def _parse_sections(text: str) -> dict[str, Any]:
    """Check which required sections are present in the markdown."""
    lower = text.lower()
    return {
        "has_prerequisites": bool(re.search(r"#+\s*prerequisit", lower)),
        "has_hatch_command": bool(re.search(r"#+\s*hatch\b", lower)),
        "has_secrets_section": bool(re.search(r"#+\s*(required\s+)?secrets?\b", lower)),
        "has_mcp_section": bool(re.search(r"#+\s*mcp\b", lower)),
        "has_verification": bool(re.search(r"#+\s*verif", lower)),
    }


def extract(egg: Egg) -> dict[str, str]:
    """Extract the per-egg AGENTS.md from the egg.

    Returns:
        ``{"AGENTS.md": <content>}`` or empty dict if absent.
    """
    if egg.agents_md is None:
        return {}

    return {"AGENTS.md": egg.agents_md}


def generate(egg: Egg, *, llm_fn: Any = None) -> dict[str, str]:
    """Generate a per-egg AGENTS.md deployment runbook.

    If the egg already has one, returns it unchanged.
    Otherwise builds one from a template, with optional LLM polish.

    Args:
        egg: Source egg.
        llm_fn: Optional callable ``(draft: str) -> str`` that polishes
                 the template output via LLM. When ``None``, the template
                 is returned as-is.

    Returns:
        ``{"AGENTS.md": <content>}``.
    """
    if egg.agents_md is not None:
        return {"AGENTS.md": egg.agents_md}

    md = _build_template(egg)

    if llm_fn is not None:
        md = llm_fn(md)

    return {"AGENTS.md": md}


def _build_template(egg: Egg) -> str:
    """Build a deployment runbook from egg data using a deterministic template."""
    m = egg.manifest
    sections: list[str] = []

    sections.append("# Deploying This Agent\n")

    lines = [
        "## Prerequisites\n",
        f"- Nydus CLI >= {m.min_nydus_version} (`pip install pynydus`)",
        f"- Target runtime: {m.agent_type.value}",
    ]
    sections.append("\n".join(lines))

    if egg.secrets.secrets:
        lines = ["## Required Secrets\n", "Before hatching, create a `.env` file with:"]
        for s in egg.secrets.secrets:
            required = "required" if s.required_at_hatch else "optional"
            desc = f" — {s.description}" if s.description else ""
            lines.append(f"- `{s.name}` ({required}){desc}")
        lines.append("")
        lines.append("Generate a template: `nydus env agent.egg -o hatch.env`")
        sections.append("\n".join(lines))

    lines = [
        "## Hatch\n",
        "```",
        f"nydus hatch agent.egg --target {m.agent_type.value} -o ./agent/",
        "```",
    ]
    if egg.secrets.secrets:
        lines[-2] += " --secrets hatch.env"
    sections.append("\n".join(lines))

    if egg.mcp.configs:
        n = len(egg.mcp.configs)
        lines = [
            "## MCP Servers\n",
            f"This agent requires {n} MCP server{'s' if n != 1 else ''}:",
        ]
        for name, cfg in egg.mcp.configs.items():
            cmd = cfg.get("command", "")
            env_keys = list(cfg.get("env", {}).keys())
            desc = f" — `{cmd}`" if cmd else ""
            if env_keys:
                desc += f" (env: {', '.join(env_keys)})"
            lines.append(f"- `{name}`{desc}")
        sections.append("\n".join(lines))

    if egg.skills.skills:
        n = len(egg.skills.skills)
        lines = [
            "## Skills\n",
            f"This agent has {n} skill{'s' if n != 1 else ''}:",
        ]
        for skill in egg.skills.skills:
            desc = skill.description or skill.name
            lines.append(f"- **{skill.name}**: {desc}")
        sections.append("\n".join(lines))

    lines = [
        "## Verify\n",
        "After hatching, confirm:",
        "- Output directory contains the expected agent files",
        "- MCP server configs are present (if applicable)",
        f"- Run `nydus inspect agent.egg` to review egg contents",
    ]
    sections.append("\n".join(lines))

    lines = [
        "## Conventions\n",
        "- Secret placeholders look like `{{SECRET_NNN}}`. Resolve before use.",
        "- Skills are in `skills/`. Each is standalone — do not merge.",
        "- Memory files in `memory/` are dated.",
    ]
    sections.append("\n".join(lines))

    return "\n\n".join(sections) + "\n"
