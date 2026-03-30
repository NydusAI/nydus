"""Tests: Eggs are target-agnostic.

Verifies that:
1. TARGET directive is rejected by the Nydusfile parser (unknown directive).
2. Manifest target list fields work correctly.
3. LLM refinement prompts contain no target-specific wording.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from pynydus.api.schemas import (
    EggPartial,
    Manifest,
    MemoryLabel,
    MemoryModule,
    MemoryRecord,
    SkillRecord,
    SkillsModule,
    SourceType,
)
from pynydus.engine.nydusfile import NydusfileError, parse
from pynydus.engine.refinement import (
    RefinedMemoryOutput,
    RefinedMemoryRecord,
    RefinedSkillRecord,
    RefinedSkillsOutput,
    _MEMORY_SYSTEM_PROMPT,
    _SKILL_SYSTEM_PROMPT,
    refine_memory,
    refine_skills,
)
from pynydus.pkg.llm import LLMTierConfig, NydusLLMConfig


# ---------------------------------------------------------------------------
# Nydusfile parsing — TARGET must be rejected
# ---------------------------------------------------------------------------


class TestTargetDirectiveRejected:
    @pytest.mark.parametrize(
        "nydusfile",
        [
            "SOURCE openclaw ./src\nTARGET openclaw\n",
            "SOURCE openclaw ./src\nTARGET letta\n",
            "SOURCE openclaw ./src\nTARGET zeroclaw\n",
            "SOURCE openclaw ./src\nTARGET OpenClaw\n",
            "SOURCE openclaw ./src\nTARGET kubernetes\n",
        ],
    )
    def test_target_line_raises_unknown_directive(self, nydusfile: str) -> None:
        with pytest.raises(NydusfileError, match="Unknown directive"):
            parse(nydusfile)

    def test_target_missing_arg_still_unknown_directive(self) -> None:
        with pytest.raises(NydusfileError, match="Unknown directive"):
            parse("SOURCE openclaw ./src\nTARGET\n")

    def test_lowercase_target_token_in_error_message(self) -> None:
        with pytest.raises(NydusfileError, match="Unknown directive 'target'"):
            parse("SOURCE openclaw ./src\ntarget letta\n")

    def test_parse_source_only(self) -> None:
        config = parse("SOURCE openclaw ./src\n")
        assert config.source == SourceType.OPENCLAW


# ---------------------------------------------------------------------------
# Manifest target list fields
# ---------------------------------------------------------------------------


class TestManifestTargetLists:
    def test_manifest_tested_targets(self) -> None:
        m = Manifest(
            nydus_version="0.1.0",
            created_at=datetime.now(tz=timezone.utc),
            source_type=SourceType.OPENCLAW,
            included_modules=["skills"],
            tested_targets=["letta", "openclaw"],
        )
        assert m.tested_targets == ["letta", "openclaw"]

    def test_manifest_recommended_targets_default(self) -> None:
        m = Manifest(
            nydus_version="0.1.0",
            created_at=datetime.now(tz=timezone.utc),
            source_type=SourceType.OPENCLAW,
            included_modules=["skills"],
        )
        assert m.recommended_targets == []

    def test_manifest_base_egg_field(self) -> None:
        m = Manifest(
            nydus_version="0.1.0",
            created_at=datetime.now(tz=timezone.utc),
            source_type=SourceType.OPENCLAW,
            included_modules=["skills"],
            base_egg="nydus/openclaw:0.2.0",
        )
        assert m.base_egg == "nydus/openclaw:0.2.0"


# ---------------------------------------------------------------------------
# LLM refinement prompts are target-agnostic
# ---------------------------------------------------------------------------


def _make_config() -> NydusLLMConfig:
    return NydusLLMConfig(
        simple=LLMTierConfig(provider="anthropic", model="test", api_key="k"),
        complex=LLMTierConfig(provider="anthropic", model="test", api_key="k"),
    )


def _make_partial_with_memory() -> EggPartial:
    return EggPartial(
        memory=MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="Hello",
                    label=MemoryLabel.STATE,
                    source_framework="test",
                    source_store="test",
                ),
            ]
        ),
    )


def _make_partial_with_skills() -> EggPartial:
    return EggPartial(
        skills=SkillsModule(
            skills=[
                SkillRecord(
                    id="s1",
                    name="Test Skill",
                    source_type="test",
                    content="Do the thing",
                ),
            ]
        ),
    )


class TestMemoryRefinementPrompt:
    @patch("pynydus.engine.refinement.create_completion")
    def test_memory_system_prompt_is_target_agnostic(self, mock_llm: MagicMock) -> None:
        mock_llm.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(
                    original_ids=["m1"],
                    text="Hello",
                    label=MemoryLabel.STATE.value,
                )
            ]
        )
        partial = _make_partial_with_memory()
        refine_memory(partial.memory, _make_config())

        call_args = mock_llm.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_msg = messages[0]["content"]
        assert system_msg == _MEMORY_SYSTEM_PROMPT
        assert "built for the" not in system_msg


class TestSkillRefinementPrompt:
    @patch("pynydus.engine.refinement.create_completion")
    def test_skill_system_prompt_is_target_agnostic(self, mock_llm: MagicMock) -> None:
        mock_llm.return_value = RefinedSkillsOutput(
            skills=[RefinedSkillRecord(original_id="s1", name="Test Skill", content="Do the thing")]
        )
        partial = _make_partial_with_skills()
        refine_skills(partial.skills, _make_config())

        call_args = mock_llm.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_msg = messages[0]["content"]
        assert system_msg == _SKILL_SYSTEM_PROMPT
        assert "built for the" not in system_msg


class TestCombinedRefinementPrompts:
    @patch("pynydus.engine.refinement.create_completion")
    def test_memory_and_skills_each_use_base_prompt(self, mock_llm: MagicMock) -> None:
        mock_llm.side_effect = [
            RefinedMemoryOutput(
                records=[
                    RefinedMemoryRecord(
                        original_ids=["m1"],
                        text="Hello",
                        label=MemoryLabel.PERSONA.value,
                    )
                ]
            ),
            RefinedSkillsOutput(
                skills=[
                    RefinedSkillRecord(original_id="s1", name="Test Skill", content="Do the thing")
                ]
            ),
        ]
        partial_mem = _make_partial_with_memory()
        partial_skill = _make_partial_with_skills()
        refine_memory(partial_mem.memory, _make_config())
        refine_skills(partial_skill.skills, _make_config())

        assert mock_llm.call_count == 2
        mem_messages = mock_llm.call_args_list[0].kwargs.get("messages")
        skill_messages = mock_llm.call_args_list[1].kwargs.get("messages")
        assert mem_messages[0]["content"] == _MEMORY_SYSTEM_PROMPT
        assert skill_messages[0]["content"] == _SKILL_SYSTEM_PROMPT
