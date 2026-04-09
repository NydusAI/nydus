"""Tests that LLM refinement steps append the expected spawn_log entries."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pynydus.api.schemas import (
    EggPartial,
    MemoryModule,
    MemoryRecord,
    SkillRecord,
    SkillsModule,
)
from pynydus.common.enums import MemoryLabel
from pynydus.engine.refinement import (
    RefinedMemoryOutput,
    RefinedMemoryRecord,
    RefinedSkillRecord,
    RefinedSkillsOutput,
    refine_memory,
    refine_skills,
)
from pynydus.llm import LLMTierConfig


@pytest.fixture()
def memory_records() -> list[MemoryRecord]:
    return [
        MemoryRecord(
            id="mem_001",
            text="I am a research assistant.",
            label=MemoryLabel.PERSONA,
            agent_type="openclaw",
            source_store="SOUL.md",
        ),
        MemoryRecord(
            id="mem_002",
            text="I help with academic papers.",
            label=MemoryLabel.PERSONA,
            agent_type="openclaw",
            source_store="SOUL.md",
        ),
        MemoryRecord(
            id="mem_003",
            text="The capital of France is Paris.",
            label=MemoryLabel.STATE,
            agent_type="openclaw",
            source_store="MEMORY.md",
        ),
    ]


@pytest.fixture()
def skill_records() -> list[SkillRecord]:
    return [
        SkillRecord(
            id="skill_001",
            name="summarize",
            agent_type="markdown_skill",
            content="Summarize a document into bullets.",
        ),
        SkillRecord(
            id="skill_002",
            name="translate",
            agent_type="markdown_skill",
            content="Translate text between languages.",
        ),
    ]


class TestMemoryMergeLogging:
    @patch("pynydus.engine.refinement.create_completion")
    def test_merge_logged(
        self,
        mock_completion: MagicMock,
        memory_records: list[MemoryRecord],
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(
                    original_ids=["mem_001", "mem_002"],
                    text="I am a research assistant helping with papers.",
                    label=MemoryLabel.PERSONA,
                ),
                RefinedMemoryRecord(
                    original_ids=["mem_003"],
                    text="The capital of France is Paris.",
                    label=MemoryLabel.STATE,
                ),
            ]
        )

        spawn_log: list[dict] = []
        refine_memory(MemoryModule(memory=memory_records), llm_config, spawn_log=spawn_log)

        merge_entries = [e for e in spawn_log if e["type"] == "memory_merge"]
        assert len(merge_entries) == 1
        assert merge_entries[0]["merged_ids"] == ["mem_001", "mem_002"]
        assert merge_entries[0]["result_id"] == "mem_merged_001"
        assert len(merge_entries[0]["original_texts_length"]) == 2

    @patch("pynydus.engine.refinement.create_completion")
    def test_refined_1to1_logged(
        self,
        mock_completion: MagicMock,
        memory_records: list[MemoryRecord],
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(
                    original_ids=["mem_001", "mem_002"],
                    text="Combined.",
                    label=MemoryLabel.PERSONA,
                ),
                RefinedMemoryRecord(
                    original_ids=["mem_003"],
                    text="Paris is the capital.",
                    label=MemoryLabel.STATE,
                ),
            ]
        )

        spawn_log: list[dict] = []
        refine_memory(MemoryModule(memory=memory_records), llm_config, spawn_log=spawn_log)

        refined_entries = [e for e in spawn_log if e["type"] == "memory_refined"]
        assert len(refined_entries) == 1
        assert refined_entries[0]["record_id"] == "mem_003"
        assert refined_entries[0]["text_changed"] is True

    @patch("pynydus.engine.refinement.create_completion")
    def test_refinement_done_logged(
        self,
        mock_completion: MagicMock,
        memory_records: list[MemoryRecord],
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(
                    original_ids=["mem_001", "mem_002"],
                    text="Combined.",
                    label=MemoryLabel.PERSONA,
                ),
                RefinedMemoryRecord(
                    original_ids=["mem_003"],
                    text="Paris is the capital.",
                    label=MemoryLabel.STATE,
                ),
            ]
        )

        spawn_log: list[dict] = []
        refine_memory(MemoryModule(memory=memory_records), llm_config, spawn_log=spawn_log)

        done_entries = [e for e in spawn_log if e["type"] == "memory_refinement_done"]
        assert len(done_entries) == 1
        assert done_entries[0]["input_count"] == 3
        assert done_entries[0]["output_count"] == 2
        assert done_entries[0]["merges"] == 1

    @patch("pynydus.engine.refinement.create_completion")
    def test_llm_failure_no_refinement_log(
        self,
        mock_completion: MagicMock,
        memory_records: list[MemoryRecord],
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = None

        spawn_log: list[dict] = []
        refine_memory(MemoryModule(memory=memory_records), llm_config, spawn_log=spawn_log)

        refinement_entries = [
            e for e in spawn_log if e["type"] in ("memory_merge", "memory_refined", "memory_refinement_done")
        ]
        assert len(refinement_entries) == 0


class TestSkillRefinedLogging:
    @patch("pynydus.engine.refinement.create_completion")
    def test_skill_refined_logged(
        self,
        mock_completion: MagicMock,
        skill_records: list[SkillRecord],
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = RefinedSkillsOutput(
            skills=[
                RefinedSkillRecord(
                    original_id="skill_001",
                    name="Summarize",
                    content="Summarize a document into bullets.",
                ),
                RefinedSkillRecord(
                    original_id="skill_002",
                    name="translate",
                    content="Translate text between languages.",
                ),
            ]
        )

        spawn_log: list[dict] = []
        refine_skills(SkillsModule(skills=skill_records), llm_config, spawn_log=spawn_log)

        skill_entries = [e for e in spawn_log if e["type"] == "skill_refined"]
        assert len(skill_entries) == 2

        assert skill_entries[0]["skill_id"] == "skill_001"
        assert skill_entries[0]["name_changed"] is True
        assert skill_entries[0]["old_name"] == "summarize"
        assert skill_entries[0]["new_name"] == "Summarize"
        assert skill_entries[0]["content_changed"] is False

        assert skill_entries[1]["skill_id"] == "skill_002"
        assert skill_entries[1]["name_changed"] is False
        assert skill_entries[1]["content_changed"] is False

    @patch("pynydus.engine.refinement.create_completion")
    def test_skill_refinement_done_logged(
        self,
        mock_completion: MagicMock,
        skill_records: list[SkillRecord],
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = RefinedSkillsOutput(
            skills=[
                RefinedSkillRecord(
                    original_id="skill_001",
                    name="Summarize",
                    content="Summarize a document into bullets.",
                ),
                RefinedSkillRecord(
                    original_id="skill_002",
                    name="translate",
                    content="Translate text between languages.",
                ),
            ]
        )

        spawn_log: list[dict] = []
        refine_skills(SkillsModule(skills=skill_records), llm_config, spawn_log=spawn_log)

        done_entries = [e for e in spawn_log if e["type"] == "skill_refinement_done"]
        assert len(done_entries) == 1
        assert done_entries[0]["input_count"] == 2
        assert done_entries[0]["output_count"] == 2

    @patch("pynydus.engine.refinement.create_completion")
    def test_llm_failure_no_skill_log(
        self,
        mock_completion: MagicMock,
        skill_records: list[SkillRecord],
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = None

        spawn_log: list[dict] = []
        refine_skills(SkillsModule(skills=skill_records), llm_config, spawn_log=spawn_log)

        skill_entries = [
            e for e in spawn_log if e["type"] in ("skill_refined", "skill_refinement_done")
        ]
        assert len(skill_entries) == 0
