"""Tests for Agent Skills SKILL.md format: parse, render, slug."""

from __future__ import annotations

import pytest
from pynydus.api.skill_format import (
    AgentSkill,
    parse_skill_md,
    render_skill_md,
    skill_slug,
)

# ---------------------------------------------------------------------------
# AgentSkill model
# ---------------------------------------------------------------------------


class TestAgentSkill:
    def test_defaults(self):
        s = AgentSkill(name="test")
        assert s.name == "test"
        assert s.description == ""
        assert s.version == "1.0"
        assert s.license == ""
        assert s.compatibility == []
        assert s.allowed_tools == []
        assert s.metadata == {}
        assert s.body == ""


# ---------------------------------------------------------------------------
# parse_skill_md
# ---------------------------------------------------------------------------


class TestParseSkillMd:
    def test_full_frontmatter(self):
        text = """\
---
name: my-skill
description: Does things
version: "2.0"
license: MIT
compatibility:
  - openclaw
  - letta
metadata:
  tags:
    - alpha
    - beta
  source_framework: letta
---

# Body

Some instructions.
"""
        skill = parse_skill_md(text)
        assert skill.name == "my-skill"
        assert skill.description == "Does things"
        assert skill.version == "2.0"
        assert skill.license == "MIT"
        assert skill.compatibility == ["openclaw", "letta"]
        assert skill.metadata["tags"] == ["alpha", "beta"]
        assert skill.metadata["source_framework"] == "letta"
        assert "# Body" in skill.body

    def test_non_spec_keys_folded_into_metadata(self):
        text = "---\nname: x\nsource_framework: letta\ntags:\n  - a\n---\nbody"
        skill = parse_skill_md(text)
        assert skill.metadata["source_framework"] == "letta"
        assert skill.metadata["tags"] == ["a"]

    def test_minimal_frontmatter(self):
        text = "---\nname: simple\n---\nHello"
        skill = parse_skill_md(text)
        assert skill.name == "simple"
        assert skill.body == "Hello"

    def test_no_frontmatter_body_only(self):
        text = "Just some markdown body content."
        skill = parse_skill_md(text)
        assert skill.name == ""
        assert skill.body == "Just some markdown body content."

    def test_empty_frontmatter(self):
        text = "---\n---\nBody here"
        skill = parse_skill_md(text)
        assert skill.name == ""
        assert skill.body == "Body here"

    @pytest.mark.parametrize("bad", ["", "   \n  \n  "])
    def test_empty_or_whitespace_raises(self, bad: str):
        with pytest.raises(ValueError, match="at least"):
            parse_skill_md(bad)

    def test_frontmatter_no_body(self):
        text = "---\nname: no-body\n---\n"
        skill = parse_skill_md(text)
        assert skill.name == "no-body"
        assert skill.body == ""

    def test_multiline_body(self):
        text = "---\nname: multi\n---\n\nLine 1\n\nLine 2\n\nLine 3"
        skill = parse_skill_md(text)
        assert "Line 1" in skill.body
        assert "Line 3" in skill.body

    def test_version_as_number(self):
        text = "---\nname: v\nversion: 3\n---\nbody"
        skill = parse_skill_md(text)
        assert skill.version == "3"


# ---------------------------------------------------------------------------
# render_skill_md
# ---------------------------------------------------------------------------


class TestRenderSkillMd:
    def test_minimal(self):
        skill = AgentSkill(name="test")
        text = render_skill_md(skill)
        assert "---" in text
        assert "name: test" in text

    def test_full_render(self):
        skill = AgentSkill(
            name="greet",
            description="Greets users",
            version="2.0",
            license="MIT",
            metadata={"tags": ["social"], "source_framework": "openclaw"},
            body="# Hello\nWorld",
        )
        text = render_skill_md(skill)
        assert "name: greet" in text
        assert "description: Greets users" in text
        assert "version: '2.0'" in text
        assert "license: MIT" in text
        assert "# Hello\nWorld" in text

    def test_description_always_present(self):
        skill = AgentSkill(name="x")
        text = render_skill_md(skill)
        assert "description: x" in text

    def test_default_version_omitted(self):
        skill = AgentSkill(name="x")
        text = render_skill_md(skill)
        assert "version" not in text

    def test_roundtrip(self):
        original = AgentSkill(
            name="roundtrip",
            description="Test roundtrip",
            version="3.0",
            license="Apache-2.0",
            compatibility=["openclaw"],
            metadata={"tags": ["a", "b"], "source_framework": "letta"},
            body="Some body content.",
        )
        text = render_skill_md(original)
        parsed = parse_skill_md(text)
        assert parsed.name == original.name
        assert parsed.description == original.description
        assert parsed.version == original.version
        assert parsed.license == original.license
        assert parsed.compatibility == original.compatibility
        assert parsed.metadata == original.metadata
        assert parsed.body == original.body


# ---------------------------------------------------------------------------
# skill_slug
# ---------------------------------------------------------------------------


class TestSkillSlug:
    def test_basic(self):
        assert skill_slug("My Cool Skill") == "my-cool-skill"

    def test_special_chars(self):
        assert skill_slug("Hello, World!") == "hello-world"

    def test_already_slug(self):
        assert skill_slug("already-slug") == "already-slug"

    def test_empty(self):
        assert skill_slug("") == "unnamed"

    def test_symbols_only(self):
        assert skill_slug("!!!") == "unnamed"

    def test_numbers(self):
        assert skill_slug("Skill 42") == "skill-42"

    def test_underscores_and_dots(self):
        assert skill_slug("my_skill.v2") == "my-skill-v2"
