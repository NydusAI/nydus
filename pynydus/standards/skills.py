"""Agent Skills standard: validate, extract.

Skills are fully deterministic (no ``generate()`` function).
"""

from __future__ import annotations

from typing import Any

from pynydus.api.schemas import Egg, ValidationIssue
from pynydus.api.skill_format import render_skill_md, skill_slug
from pynydus.standards._loader import validate_against_schema


def validate(egg: Egg, schema: dict[str, Any] | None = None) -> list[ValidationIssue]:
    """Validate each skill's frontmatter against the agentskills.io schema.

    Args:
        egg: The Egg whose skills are validated.
        schema: Optional JSON Schema dict. When ``None``, the schema is loaded
            from the bundled ``agentskills`` spec.

    Returns:
        List of validation issues (empty if valid or if there are no skills).
    """
    if not egg.skills.skills:
        return []

    issues: list[ValidationIssue] = []
    for skill in egg.skills.skills:
        frontmatter: dict[str, Any] = {"name": skill.name}
        if skill.description:
            frontmatter["description"] = skill.description
        if skill.version and skill.version != "1.0":
            frontmatter["version"] = skill.version
        if skill.license:
            frontmatter["license"] = skill.license
        if skill.compatibility:
            frontmatter["compatibility"] = skill.compatibility
        if skill.allowed_tools:
            frontmatter["allowed-tools"] = " ".join(skill.allowed_tools)
        if skill.metadata:
            frontmatter["metadata"] = skill.metadata

        slug = skill_slug(skill.name)
        issues.extend(
            validate_against_schema(
                frontmatter,
                "agentskills",
                schema=schema,
                label=f"Skill '{skill.name}'",
                location=f"skills/{slug}/SKILL.md",
            )
        )

    return issues


def extract(egg: Egg) -> dict[str, str]:
    """Extract all skills as SKILL.md files.

    Args:
        egg: The Egg containing skill definitions.

    Returns:
        ``{"skills/<slug>/SKILL.md": <content>, ...}`` for each skill.
    """
    result: dict[str, str] = {}
    for skill in egg.skills.skills:
        slug = skill_slug(skill.name)
        result[f"skills/{slug}/SKILL.md"] = render_skill_md(skill)
    return result
