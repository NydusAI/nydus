"""Opt-in live LLM integration tests.

Requires ``NYDUS_LLM_TYPE`` and ``NYDUS_LLM_API_KEY`` to be set.
Run with: ``pytest -m live_llm``
"""

from __future__ import annotations

import os

import pytest
from pynydus.api.schemas import AgentSkill, MemoryModule, MemoryRecord, SkillsModule
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
                    source_store="MEMORY.md",
                ),
                MemoryRecord(
                    id="mem_002",
                    text="Python was first released in 1991 by Guido van Rossum.",
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="MEMORY.md",
                ),
            ]
        )
        result = refine_memory(memory, tier)
        assert len(result.memory) < 2, "Near-duplicates should be merged into one record"
        assert any("1991" in m.text for m in result.memory)

    def test_placeholders_survive(self):
        """Redaction tokens in memory text must survive spawn-time refinement."""
        tier = _tier()
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="Contact {{PII_001}} or use key {{SECRET_001}} for the API.",
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="MEMORY.md",
                ),
            ]
        )
        result = refine_memory(memory, tier)
        assert len(result.memory) >= 1
        combined = "\n".join(m.text for m in result.memory)
        assert "{{PII_001}}" in combined
        assert "{{SECRET_001}}" in combined


@skip_if_no_key
class TestLiveSkills:
    def test_polish(self):
        tier = _tier()
        skills = SkillsModule(
            skills=[
                AgentSkill(
                    name="Summarize",
                    description="",
                    body="take text and make it shorter",
                    metadata={"id": "skill_001", "source_framework": "openclaw"},
                )
            ]
        )
        result = refine_skills(skills, tier)
        assert result.skills[0].body
        assert result.skills[0].body != "take text and make it shorter", (
            "LLM should refine the sloppy skill description"
        )

    def test_placeholders_survive(self):
        """Redaction tokens in skill content must survive spawn-time refinement."""
        tier = _tier()
        skills = SkillsModule(
            skills=[
                AgentSkill(
                    name="API helper",
                    description="",
                    body=(
                        "Call the endpoint with header Auth: {{SECRET_001}} "
                        "and email {{PII_001}} for the account."
                    ),
                    metadata={"id": "skill_001", "source_framework": "openclaw"},
                )
            ]
        )
        result = refine_skills(skills, tier)
        assert len(result.skills) == 1
        assert result.skills[0].metadata.get("id") == "skill_001"
        text = result.skills[0].body
        assert "{{PII_001}}" in text
        assert "{{SECRET_001}}" in text


@skip_if_no_key
class TestLiveHatch:
    def test_polish(self):
        """Hatch refinement returns a valid SOUL.md (unchanged is OK).

        ``refine_hatch`` asks the model to return only files it changed. omitting
        a file leaves the input as-is. Identical output is therefore valid.
        """
        tier = _tier()
        egg = make_egg()
        files = {"SOUL.md": "I am a helpful AI assistant.\n"}
        result = refine_hatch(files, egg, tier, target="openclaw")
        assert "SOUL.md" in result
        assert len(result["SOUL.md"]) > 0

    def test_placeholders_survive(self):
        """Redaction tokens must survive hatch refinement (with retry/fallback)."""
        tier = _tier()
        egg = make_egg()
        files = {
            "USER.md": (
                "The user's name is {{PII_001}} and their API key is {{SECRET_001}}. "
                "They prefer dark mode and use metric units.\n"
            ),
        }
        result = refine_hatch(files, egg, tier, target="openclaw")
        assert "{{PII_001}}" in result["USER.md"]
        assert "{{SECRET_001}}" in result["USER.md"]
