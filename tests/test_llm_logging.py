"""Tests for LLM vendor logging (Priority 1.3).

Verifies that every LLM call is logged as a ``{"type": "llm_call", ...}``
entry with provider, model, latency, and response_model fields.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from pynydus.api.schemas import (
    Egg,
    EggPartial,
    MemoryLabel,
    MemoryModule,
    MemoryRecord,
    SkillRecord,
    SkillsModule,
)
from pynydus.engine.refinement import (
    AdaptedFilesOutput,
    RefinedMemoryOutput,
    RefinedMemoryRecord,
    RefinedSkillRecord,
    RefinedSkillsOutput,
    refine_hatch,
    refine_memory,
    refine_skills,
)
from pynydus.pkg.llm import LLMTierConfig, create_completion


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_partial() -> EggPartial:
    return EggPartial(
        skills=SkillsModule(
            skills=[
                SkillRecord(
                    id="skill_001",
                    name="test skill",
                    source_type="markdown_skill",
                    content="Test content.",
                )
            ]
        ),
        memory=MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="A fact.",
                    label=MemoryLabel.STATE,
                    source_framework="openclaw",
                    source_store="knowledge.md",
                )
            ]
        ),
    )


# ---------------------------------------------------------------------------
# create_completion logging
# ---------------------------------------------------------------------------


class DummyResponse(BaseModel):
    answer: str


class TestCreateCompletionLogging:
    @patch("pynydus.pkg.llm.create_client")
    def test_log_entry_appended(self, mock_create_client: MagicMock):
        """When log is provided, an llm_call entry is appended."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = DummyResponse(answer="hi")
        mock_create_client.return_value = mock_client

        tier = LLMTierConfig(provider="anthropic", model="claude-3", api_key="test")
        log: list[dict] = []

        result = create_completion(
            tier,
            messages=[{"role": "user", "content": "hello"}],
            response_model=DummyResponse,
            log=log,
        )

        assert result.answer == "hi"
        assert len(log) == 1
        entry = log[0]
        assert entry["type"] == "llm_call"
        assert entry["provider"] == "anthropic"
        assert entry["model"] == "claude-3"
        assert entry["response_model"] == "DummyResponse"
        assert isinstance(entry["latency_ms"], int)
        assert entry["latency_ms"] >= 0

    @patch("pynydus.pkg.llm.create_client")
    def test_no_log_no_entry(self, mock_create_client: MagicMock):
        """When log is None (default), nothing is appended."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = DummyResponse(answer="hi")
        mock_create_client.return_value = mock_client

        tier = LLMTierConfig(provider="anthropic", model="claude-3", api_key="test")

        result = create_completion(
            tier,
            messages=[{"role": "user", "content": "hello"}],
            response_model=DummyResponse,
        )
        assert result.answer == "hi"

    @patch("pynydus.pkg.llm.create_client")
    def test_multiple_calls_accumulate(self, mock_create_client: MagicMock):
        """Multiple calls with the same log list accumulate entries."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = DummyResponse(answer="hi")
        mock_create_client.return_value = mock_client

        tier = LLMTierConfig(provider="openai", model="gpt-4o", api_key="test")
        log: list[dict] = []

        create_completion(tier, messages=[], response_model=DummyResponse, log=log)
        create_completion(tier, messages=[], response_model=DummyResponse, log=log)

        assert len(log) == 2
        assert all(e["provider"] == "openai" for e in log)

    @patch("pynydus.pkg.llm.create_client")
    def test_exception_returns_none_and_does_not_log(self, mock_create_client: MagicMock):
        """If the LLM call raises, None is returned and no entry is logged."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("API down")
        mock_create_client.return_value = mock_client

        tier = LLMTierConfig(provider="anthropic", model="claude-3", api_key="test")
        log: list[dict] = []

        result = create_completion(tier, messages=[], response_model=DummyResponse, log=log)

        assert result is None
        assert len(log) == 0


# ---------------------------------------------------------------------------
# Spawn refinement logging
# ---------------------------------------------------------------------------


class TestSpawnRefinementLogging:
    @patch("pynydus.engine.refinement.create_completion")
    def test_refine_memory_logs_llm_calls(
        self,
        mock_completion: MagicMock,
        sample_partial: EggPartial,
        llm_config: NydusLLMConfig,
    ):
        """refine_memory passes spawn_log to create_completion so LLM calls are logged."""
        spawn_log: list[dict] = []
        mock_completion.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(
                    original_ids=["mem_001"],
                    text="A fact.",
                    label=MemoryLabel.STATE,
                )
            ]
        )

        refine_memory(sample_partial.memory, llm_config, spawn_log=spawn_log)

        mock_completion.assert_called_once()
        assert "log" in mock_completion.call_args.kwargs

    @patch("pynydus.engine.refinement.create_completion")
    def test_refine_skills_logs_llm_calls(
        self,
        mock_completion: MagicMock,
        sample_partial: EggPartial,
        llm_config: NydusLLMConfig,
    ):
        """refine_skills passes spawn_log to create_completion so LLM calls are logged."""
        spawn_log: list[dict] = []
        mock_completion.return_value = RefinedSkillsOutput(
            skills=[
                RefinedSkillRecord(
                    original_id="skill_001",
                    name="test skill",
                    content="Test content.",
                )
            ]
        )

        refine_skills(sample_partial.skills, llm_config, spawn_log=spawn_log)

        mock_completion.assert_called_once()
        assert "log" in mock_completion.call_args.kwargs


# ---------------------------------------------------------------------------
# Hatch refinement logging
# ---------------------------------------------------------------------------


class TestHatchRefinementLogging:
    @patch("pynydus.engine.refinement.create_completion")
    def test_hatch_passes_log(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: NydusLLMConfig,
    ):
        """refine_hatch forwards the log parameter to create_completion."""
        file_dict = {"soul.md": "Content"}
        mock_completion.return_value = AdaptedFilesOutput(files=[])

        hatch_log: list[dict] = []
        refine_hatch(file_dict, minimal_egg, llm_config, log=hatch_log)

        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["log"] is hatch_log

    @patch("pynydus.engine.refinement.create_completion")
    def test_hatch_no_log_default(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: NydusLLMConfig,
    ):
        """refine_hatch with no log argument passes log=None."""
        file_dict = {"soul.md": "Content"}
        mock_completion.return_value = AdaptedFilesOutput(files=[])

        refine_hatch(file_dict, minimal_egg, llm_config)

        call_kwargs = mock_completion.call_args.kwargs
        assert call_kwargs["log"] is None
