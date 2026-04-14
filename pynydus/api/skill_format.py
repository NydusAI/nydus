"""Agent Skills format: SKILL.md parse / render.

Implements the agentskills.io directory convention:
    skills/<slug>/SKILL.md

Each SKILL.md has YAML front-matter (between ``---`` fences) followed by a
Markdown body.  The frontmatter fields follow the Agent Skills spec:

    name          (required)  Slug-style identifier, max 64 chars
    description   (required)  Human-readable summary
    version       (optional)  SemVer string, defaults to "1.0"
    license       (optional)  SPDX identifier
    compatibility (optional)  List of compatible runtimes
    allowed-tools (optional)  List of permitted tool names
    metadata      (optional)  Arbitrary key-value pairs

Non-spec fields (e.g. ``agent_type``, ``tags``) are stored inside the
``metadata`` map so the frontmatter remains spec-compliant.
"""

from __future__ import annotations

import re
from typing import Any

import yaml
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# AgentSkill model
# ---------------------------------------------------------------------------


class AgentSkill(BaseModel):
    """Spec-compliant representation of a single Agent Skill (agentskills.io)."""

    name: str
    description: str = ""
    version: str = "1.0"
    license: str = ""
    compatibility: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    body: str = ""
    """Markdown body: the main skill content (instructions, code, etc.)."""


# ---------------------------------------------------------------------------
# Parse / render
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"\A\s*---\s*\n(.*?)---\s*\n?(.*)",
    re.DOTALL,
)


def parse_skill_md(text: str) -> AgentSkill:
    """Parse a SKILL.md string into ``AgentSkill``.

    Args:
        text: Full file contents. optional YAML front-matter (``---`` fences)
            then Markdown body. Spec fields are parsed. unknown keys go into
            ``metadata``.

    Returns:
        Parsed skill model.

    Raises:
        ValueError: If there is no name and no body.
    """
    m = _FRONTMATTER_RE.match(text)
    if m:
        raw_yaml = m.group(1)
        body = m.group(2).strip()
        meta: dict[str, Any] = yaml.safe_load(raw_yaml) or {}
    else:
        meta = {}
        body = text.strip()

    if "name" not in meta and not body:
        raise ValueError("SKILL.md must contain at least a name in front-matter or a body")

    _SPEC_KEYS = {
        "name",
        "description",
        "version",
        "license",
        "compatibility",
        "allowed-tools",
        "metadata",
    }
    extra: dict[str, Any] = {}
    for key in list(meta):
        if key not in _SPEC_KEYS:
            extra[key] = meta.pop(key)

    user_metadata: dict[str, Any] = meta.get("metadata", {})
    if isinstance(user_metadata, dict):
        extra.update(user_metadata)
    merged_metadata = extra

    return AgentSkill(
        name=meta.get("name", ""),
        description=meta.get("description", ""),
        version=str(meta.get("version", "1.0")),
        license=meta.get("license", ""),
        compatibility=meta.get("compatibility", []),
        allowed_tools=meta.get("allowed-tools", []),
        metadata=merged_metadata,
        body=body,
    )


def render_skill_md(skill: AgentSkill) -> str:
    """Serialize ``AgentSkill`` to spec-compliant SKILL.md text.

    Args:
        skill: Parsed or constructed skill model.

    Returns:
        Front-matter plus body string.

    Note:
        Only spec keys are top-level YAML fields. extra data stays under
        ``metadata``.
    """
    meta: dict[str, Any] = {"name": skill.name}
    meta["description"] = skill.description or skill.name
    if skill.version and skill.version != "1.0":
        meta["version"] = skill.version
    if skill.license:
        meta["license"] = skill.license
    if skill.compatibility:
        meta["compatibility"] = skill.compatibility
    if skill.allowed_tools:
        meta["allowed-tools"] = skill.allowed_tools
    if skill.metadata:
        meta["metadata"] = dict(skill.metadata)

    yaml_block = yaml.dump(meta, default_flow_style=False, sort_keys=False).strip()
    parts = [f"---\n{yaml_block}\n---"]
    if skill.body:
        parts.append(skill.body)
    return "\n\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Slug helper
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_CONSECUTIVE_HYPHENS = re.compile(r"-{2,}")


def skill_slug(name: str) -> str:
    """Convert a display name to a filesystem-safe slug.

    Args:
        name: Human-readable skill name.

    Returns:
        Lowercase slug (max 64 chars, no repeated or edge hyphens).

    Examples:
        >>> skill_slug("My Cool Skill!")
        'my-cool-skill'
    """
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    slug = _CONSECUTIVE_HYPHENS.sub("-", slug)
    slug = slug[:64].rstrip("-")
    return slug or "unnamed"
