"""A2A Agent Card standard: validate, extract, generate.

Passthrough-first: if the source project already contains ``agent-card.json``,
Nydus copies it verbatim. Otherwise, Nydus generates a card from egg data.
"""

from __future__ import annotations

import json
from typing import Any

from pynydus.api.schemas import Egg, ValidationIssue
from pynydus.api.skill_format import skill_slug
from pynydus.common.enums import MemoryLabel
from pynydus.standards._loader import validate_against_schema


def validate(egg: Egg, schema: dict[str, Any] | None = None) -> list[ValidationIssue]:
    """Validate the egg's A2A agent card against the spec schema.

    Args:
        egg: The Egg to validate.
        schema: Optional JSON Schema dict. When ``None``, the schema is loaded
            from the bundled ``a2a`` spec.

    Returns:
        List of validation issues (empty if valid or if the egg has no agent card).
    """
    if egg.a2a_card is None:
        return []

    return validate_against_schema(
        egg.a2a_card,
        "a2a",
        schema=schema,
        label="A2A agent card",
        location="agent-card.json",
    )


def extract(egg: Egg) -> dict[str, str]:
    """Extract the A2A agent card from the egg.

    Args:
        egg: The Egg that may contain a passthrough A2A agent card.

    Returns:
        ``{"agent-card.json": <content>}`` or empty dict if absent.
    """
    if egg.a2a_card is None:
        return {}

    return {"agent-card.json": json.dumps(egg.a2a_card, indent=2) + "\n"}


def generate(egg: Egg, *, llm_fn: Any = None) -> dict[str, str]:
    """Generate an A2A agent card from egg contents.

    If the egg already has a passthrough card, returns it unchanged.
    Otherwise builds one deterministically, with optional LLM enhancement.

    Args:
        egg: Source egg.
        llm_fn: Optional callable ``(card_draft: dict) -> dict`` that
                 enhances name, description, and skill descriptions via LLM.
                 When ``None``, deterministic fallbacks are used.

    Returns:
        ``{"agent-card.json": <content>}``.
    """
    if egg.a2a_card is not None:
        return {"agent-card.json": json.dumps(egg.a2a_card, indent=2) + "\n"}

    card = _build_deterministic_card(egg)

    if llm_fn is not None:
        card = llm_fn(card)

    return {"agent-card.json": json.dumps(card, indent=2) + "\n"}


def _build_deterministic_card(egg: Egg) -> dict[str, Any]:
    """Build an agent card using only deterministic data from the egg."""
    name = egg.manifest.agent_name or egg.manifest.agent_type.value

    description = egg.manifest.agent_description or ""
    if not description:
        persona_records = [m for m in egg.memory.memory if m.label == MemoryLabel.PERSONA]
        if persona_records:
            description = persona_records[0].text[:500]

    if not description:
        description = f"A {egg.manifest.agent_type.value} agent."

    skills: list[dict[str, Any]] = []
    for skill in egg.skills.skills:
        slug = skill_slug(skill.name)
        tags = skill.metadata.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        skills.append(
            {
                "id": skill.metadata.get("id", slug),
                "name": skill.name,
                "description": skill.description or skill.name,
                "tags": tags,
            }
        )

    return {
        "name": name,
        "description": description,
        "version": egg.manifest.egg_version,
        "supportedInterfaces": [],
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": skills,
    }
