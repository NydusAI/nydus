"""LLM refinement contract tests.

No live LLM calls. Validates that the refinement functions correctly handle
merge IDs, unknown IDs, placeholder survival, graceful degradation, and
prompt construction.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pynydus.api.schemas import AgentSkill, MemoryModule, MemoryRecord, SkillsModule
from pynydus.common.enums import AgentType, MemoryLabel
from pynydus.engine.refinement import (
    AdaptedFile,
    AdaptedFilesOutput,
    RefinedMemoryOutput,
    RefinedMemoryRecord,
    RefinedSkillRecord,
    RefinedSkillsOutput,
    refine_hatch,
    refine_memory,
    refine_skills,
)
from pynydus.llm import LLMTierConfig

from conftest import make_egg


@pytest.fixture
def tier():
    return LLMTierConfig(provider="openai", model="gpt-4o", api_key="sk-test")


class TestMemoryRefinement:
    @patch("pynydus.engine.refinement.create_completion")
    def test_merge_ids(self, mock_comp, tier):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="Python is great.",
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="k.md",
                ),
                MemoryRecord(
                    id="mem_002",
                    text="Python is awesome.",
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="k.md",
                ),
            ]
        )
        mock_comp.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(
                    original_ids=["mem_001", "mem_002"],
                    text="Python is great and awesome.",
                    label=MemoryLabel.STATE,
                )
            ]
        )
        result = refine_memory(memory, tier)
        assert len(result.memory) == 1
        assert result.memory[0].id.startswith("mem_merged_")
        assert "great" in result.memory[0].text
        assert "awesome" in result.memory[0].text

    @patch("pynydus.engine.refinement.create_completion")
    def test_unknown_id_skipped(self, mock_comp, tier):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="Real.",
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="k.md",
                ),
            ]
        )
        mock_comp.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(
                    original_ids=["mem_001"], text="Real.", label=MemoryLabel.STATE
                ),
                RefinedMemoryRecord(
                    original_ids=["nonexistent_id"], text="Hallucinated.", label=MemoryLabel.STATE
                ),
            ]
        )
        result = refine_memory(memory, tier)
        assert len(result.memory) == 1
        assert result.memory[0].text == "Real."


class TestSkillsRefinement:
    @patch("pynydus.engine.refinement.create_completion")
    def test_unknown_id_skipped(self, mock_comp, tier):
        skills = SkillsModule(
            skills=[
                AgentSkill(
                    name="Search",
                    description="",
                    body="Search the web.",
                    metadata={"id": "skill_001", "source_framework": "openclaw"},
                ),
            ]
        )
        mock_comp.return_value = RefinedSkillsOutput(
            skills=[
                RefinedSkillRecord(
                    original_id="skill_001", name="Search", content="Search the web."
                ),
                RefinedSkillRecord(
                    original_id="skill_999", name="Ghost", content="Does not exist."
                ),
            ]
        )
        result = refine_skills(skills, tier)
        assert len(result.skills) == 1
        assert result.skills[0].name == "Search"


class TestHatchRefinement:
    @patch("pynydus.engine.refinement.create_completion")
    def test_only_changed_files(self, mock_comp, tier):
        mock_comp.return_value = AdaptedFilesOutput(
            files=[
                AdaptedFile(path="SOUL.md", content="Refined soul."),
            ]
        )
        egg = make_egg()
        original = {"SOUL.md": "Original soul.", "MEMORY.md": "A fact.", "AGENTS.md": "Rules."}
        result = refine_hatch(original, egg, tier, target="openclaw")
        assert result["SOUL.md"] == "Refined soul."
        assert result["MEMORY.md"] == "A fact."
        assert result["AGENTS.md"] == "Rules."


class TestPlaceholderSurvival:
    @patch("pynydus.engine.refinement.create_completion")
    def test_placeholders_survive(self, mock_comp, tier):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="Contact {{PII_001}} at {{SECRET_001}}.",
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="SOUL.md",
                )
            ]
        )
        mock_comp.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(
                    original_ids=["mem_001"],
                    text="Contact {{PII_001}} at {{SECRET_001}}.",
                    label=MemoryLabel.STATE,
                )
            ]
        )
        result = refine_memory(memory, tier)
        assert "{{PII_001}}" in result.memory[0].text
        assert "{{SECRET_001}}" in result.memory[0].text


class TestGracefulDegradation:
    @patch("pynydus.engine.refinement.create_completion", return_value=None)
    def test_memory_fallback(self, _mock, tier):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="Original.",
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="MEMORY.md",
                )
            ]
        )
        result = refine_memory(memory, tier)
        assert result.memory[0].text == "Original."

    @patch("pynydus.engine.refinement.create_completion", return_value=None)
    def test_skills_fallback(self, _mock, tier):
        skills = SkillsModule(
            skills=[
                AgentSkill(
                    name="test",
                    description="",
                    body="content",
                    metadata={"id": "s1", "source_framework": "openclaw"},
                )
            ]
        )
        result = refine_skills(skills, tier)
        assert result.skills[0].name == "test"

    @patch("pynydus.engine.refinement.create_completion")
    def test_unknown_paths_ignored(self, mock_comp, tier):
        mock_comp.return_value = AdaptedFilesOutput(
            files=[
                AdaptedFile(path="SOUL.md", content="Adapted"),
                AdaptedFile(path="malicious.md", content="Should not appear"),
            ]
        )
        egg = make_egg()
        result = refine_hatch({"SOUL.md": "Original"}, egg, tier, target="openclaw")
        assert result["SOUL.md"] == "Adapted"
        assert "malicious.md" not in result


class TestPromptConstruction:
    @patch("pynydus.engine.refinement.create_completion")
    def test_cross_platform_adapt(self, mock_comp, tier):
        mock_comp.return_value = AdaptedFilesOutput(files=[])
        egg = make_egg(agent_type=AgentType.OPENCLAW)
        refine_hatch({"agent_state.json": '{"memory": {}}'}, egg, tier, target="letta")
        call_args = mock_comp.call_args
        messages = call_args[1].get("messages") or call_args[0][2]
        assert "adapt" in messages[0]["content"].lower()

    @patch("pynydus.engine.refinement.create_completion")
    def test_same_platform_polish(self, mock_comp, tier):
        mock_comp.return_value = AdaptedFilesOutput(files=[])
        egg = make_egg(agent_type=AgentType.OPENCLAW)
        refine_hatch({"SOUL.md": "Content"}, egg, tier, target="openclaw")
        call_args = mock_comp.call_args
        messages = call_args[1].get("messages") or call_args[0][2]
        assert "polish" in messages[0]["content"].lower()
