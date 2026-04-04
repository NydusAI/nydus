"""Opt-in live LLM integration tests.

Requires ``NYDUS_LLM_TYPE`` and ``NYDUS_LLM_API_KEY`` to be set.
Run with: ``pytest -m live_llm``
"""

from __future__ import annotations

import os

import pytest
from pynydus.api.schemas import MemoryModule, MemoryRecord, SkillRecord, SkillsModule
from pynydus.common.enums import MemoryLabel
from pynydus.engine.refinement import refine_hatch, refine_memory, refine_skills
from pynydus.llm import LLMTierConfig

from conftest import make_egg

pytestmark = pytest.mark.live_llm

_SKIP = not (os.getenv("NYDUS_LLM_TYPE") and os.getenv("NYDUS_LLM_API_KEY"))
skip_if_no_key = pytest.mark.skipif(_SKIP, reason="NYDUS_LLM_API_KEY not set")


def _tier() -> LLMTierConfig:
    llm_type = os.environ["NYDUS_LLM_TYPE"]
    parts = llm_type.split("/", 1)
    provider = parts[0]
    model = parts[1] if len(parts) > 1 else parts[0]
    return LLMTierConfig(provider=provider, model=model, api_key=os.environ["NYDUS_LLM_API_KEY"])


@skip_if_no_key
class TestLiveMemory:
    def test_dedup(self):
        tier = _tier()
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="Python was released in 1991.",
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="knowledge.md",
                ),
                MemoryRecord(
                    id="mem_002",
                    text="Python was first released in 1991 by Guido van Rossum.",
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="knowledge.md",
                ),
            ]
        )
        result = refine_memory(memory, tier)
        assert len(result.memory) < 2, "Near-duplicates should be merged into one record"
        assert any("1991" in m.text for m in result.memory)


@skip_if_no_key
class TestLiveSkills:
    def test_polish(self):
        tier = _tier()
        skills = SkillsModule(
            skills=[
                SkillRecord(
                    id="skill_001",
                    name="Summarize",
                    agent_type="openclaw",
                    content="take text and make it shorter",
                )
            ]
        )
        result = refine_skills(skills, tier)
        assert result.skills[0].content
        assert result.skills[0].content != "take text and make it shorter", (
            "LLM should refine the sloppy skill description"
        )


@skip_if_no_key
class TestLiveHatch:
    def test_polish(self):
        tier = _tier()
        egg = make_egg()
        files = {"soul.md": "I am a helpful AI assistant.\n"}
        result = refine_hatch(files, egg, tier)
        assert "soul.md" in result
        assert len(result["soul.md"]) > 0
        assert result["soul.md"] != files["soul.md"], (
            "LLM should polish content, not return it unchanged"
        )

    def test_placeholders_survive(self):
        tier = _tier()
        egg = make_egg()
        files = {"soul.md": "Contact me at {{PII_001}} or {{SECRET_001}}.\n"}
        result = refine_hatch(files, egg, tier)
        assert "{{PII_001}}" in result["soul.md"]
        assert "{{SECRET_001}}" in result["soul.md"]
