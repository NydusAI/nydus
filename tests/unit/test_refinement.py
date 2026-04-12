"""Tests for LLM refinement logic (engine/refinement.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from pynydus.api.schemas import (
    Egg,
    EggPartial,
    MemoryModule,
    MemoryRecord,
    SkillRecord,
    SkillsModule,
)
from pynydus.common.enums import MemoryLabel
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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_memory_records() -> list[MemoryRecord]:
    return [
        MemoryRecord(
            id="mem_001",
            text="I am a research assistant.",
            label=MemoryLabel.PERSONA,
            agent_type="openclaw",
            source_store="SOUL.md",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        MemoryRecord(
            id="mem_002",
            text="I'm a research assistant that helps with papers.",
            label=MemoryLabel.PERSONA,
            agent_type="openclaw",
            source_store="SOUL.md",
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        ),
        MemoryRecord(
            id="mem_003",
            text="The capital of France is Paris.",
            label=MemoryLabel.STATE,
            agent_type="openclaw",
            source_store="MEMORY.md",
        ),
    ]


@pytest.fixture
def sample_skill_records() -> list[SkillRecord]:
    return [
        SkillRecord(
            id="skill_001",
            name="  summarize Documents  ",
            agent_type="markdown_skill",
            content="Given a document, produce a 5-bullet summary.\n\n",
            metadata={"path": "skill.md"},
        ),
        SkillRecord(
            id="skill_002",
            name="translate_text",
            agent_type="markdown_skill",
            content="Translate text between English and French",
            metadata={"path": "skill.md"},
        ),
    ]


@pytest.fixture
def sample_partial(
    sample_memory_records: list[MemoryRecord],
    sample_skill_records: list[SkillRecord],
) -> EggPartial:
    return EggPartial(
        skills=SkillsModule(skills=sample_skill_records),
        memory=MemoryModule(memory=sample_memory_records),
    )


# ---------------------------------------------------------------------------
# Response model validation
# ---------------------------------------------------------------------------


class TestResponseModels:
    def test_refined_memory_output_valid(self):
        output = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(
                    original_ids=["mem_001", "mem_002"],
                    text="I am a research assistant.",
                    label=MemoryLabel.PERSONA,
                )
            ]
        )
        assert len(output.records) == 1
        assert output.records[0].original_ids == ["mem_001", "mem_002"]

    def test_refined_memory_record_requires_original_ids(self):
        with pytest.raises(ValidationError):
            RefinedMemoryRecord(text="test")  # type: ignore[call-arg]

    def test_refined_skills_output_valid(self):
        output = RefinedSkillsOutput(
            skills=[
                RefinedSkillRecord(
                    original_id="skill_001",
                    name="Summarize Documents",
                    content="Given a document, produce a 5-bullet summary.",
                )
            ]
        )
        assert len(output.skills) == 1

    def test_adapted_files_output_valid(self):
        output = AdaptedFilesOutput(
            files=[AdaptedFile(path="SOUL.md", content="Updated content")],
            warnings=["Minor formatting issue"],
        )
        assert len(output.files) == 1
        assert len(output.warnings) == 1

    def test_adapted_files_output_default_warnings(self):
        output = AdaptedFilesOutput(files=[])
        assert output.warnings == []


# ---------------------------------------------------------------------------
# refine_memory: memory deduplication
# ---------------------------------------------------------------------------


class TestRefineMemory:
    @patch("pynydus.engine.refinement.create_completion")
    def test_deduplicates_memory(
        self,
        mock_completion: MagicMock,
        sample_partial: EggPartial,
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(
                    original_ids=["mem_001", "mem_002"],
                    text="I am a research assistant that helps with papers.",
                    label=MemoryLabel.PERSONA,
                ),
                RefinedMemoryRecord(
                    original_ids=["mem_003"],
                    text="The capital of France is Paris.",
                    label=MemoryLabel.STATE,
                ),
            ]
        )

        result = refine_memory(sample_partial.memory, llm_config)

        assert len(result.memory) == 2
        merged = result.memory[0]
        assert merged.id == "mem_merged_001"
        assert merged.label == MemoryLabel.PERSONA
        assert merged.agent_type == "openclaw"
        assert merged.source_store == "SOUL.md"
        fact = result.memory[1]
        assert fact.id == "mem_003"

    @patch("pynydus.engine.refinement.create_completion")
    def test_failure_returns_original(
        self,
        mock_completion: MagicMock,
        sample_partial: EggPartial,
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = None
        original_count = len(sample_partial.memory.memory)

        result = refine_memory(sample_partial.memory, llm_config)

        assert len(result.memory) == original_count
        assert result.memory[0].id == "mem_001"

    @patch("pynydus.engine.refinement.create_completion")
    def test_empty_memory_skips_llm(
        self,
        mock_completion: MagicMock,
        llm_config: LLMTierConfig,
    ):
        result = refine_memory(MemoryModule(memory=[]), llm_config)
        assert result.memory == []

    @patch("pynydus.engine.refinement.create_completion")
    def test_preserves_placeholder_tokens(
        self,
        mock_completion: MagicMock,
        llm_config: LLMTierConfig,
    ):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="Contact {{PII_001}} at {{PII_002}}.",
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="MEMORY.md",
                ),
            ]
        )
        mock_completion.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(
                    original_ids=["mem_001"],
                    text="Contact {{PII_001}} at {{PII_002}}.",
                    label=MemoryLabel.STATE,
                ),
            ]
        )

        result = refine_memory(memory, llm_config)

        assert "{{PII_001}}" in result.memory[0].text
        assert "{{PII_002}}" in result.memory[0].text


# ---------------------------------------------------------------------------
# refine_skills: skill cleanup
# ---------------------------------------------------------------------------


class TestRefineSkills:
    @patch("pynydus.engine.refinement.create_completion")
    def test_cleans_skills(
        self,
        mock_completion: MagicMock,
        sample_partial: EggPartial,
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = RefinedSkillsOutput(
            skills=[
                RefinedSkillRecord(
                    original_id="skill_001",
                    name="Summarize Documents",
                    content="Given a document, produce a 5-bullet summary.",
                ),
                RefinedSkillRecord(
                    original_id="skill_002",
                    name="Translate Text",
                    content="Translate text between English and French.",
                ),
            ]
        )

        result = refine_skills(sample_partial.skills, llm_config)

        assert result.skills[0].name == "Summarize Documents"
        assert result.skills[1].name == "Translate Text"
        assert result.skills[0].agent_type == "markdown_skill"
        assert result.skills[0].metadata == {"path": "skill.md"}

    @patch("pynydus.engine.refinement.create_completion")
    def test_skill_failure_returns_original(
        self,
        mock_completion: MagicMock,
        llm_config: LLMTierConfig,
    ):
        skills = SkillsModule(
            skills=[
                SkillRecord(
                    id="skill_001",
                    name="test",
                    agent_type="markdown_skill",
                    content="content",
                )
            ]
        )
        mock_completion.return_value = None

        result = refine_skills(skills, llm_config)

        assert len(result.skills) == 1
        assert result.skills[0].name == "test"

    @patch("pynydus.engine.refinement.create_completion")
    def test_empty_skills_skips_llm(
        self,
        mock_completion: MagicMock,
        llm_config: LLMTierConfig,
    ):
        result = refine_skills(SkillsModule(skills=[]), llm_config)
        assert result.skills == []


# ---------------------------------------------------------------------------
# refine_hatch
# ---------------------------------------------------------------------------


class TestRefineHatch:
    @patch("pynydus.engine.refinement.create_completion")
    def test_adapts_files(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        file_dict = {"SOUL.md": "Original soul content", "skill.md": "Original skill content"}

        mock_completion.return_value = AdaptedFilesOutput(
            files=[
                AdaptedFile(path="SOUL.md", content="Adapted soul content for Letta"),
            ],
        )

        result = refine_hatch(file_dict, minimal_egg, llm_config)

        assert result["SOUL.md"] == "Adapted soul content for Letta"
        assert result["skill.md"] == "Original skill content"

    @patch("pynydus.engine.refinement.create_completion")
    def test_same_platform_uses_polish_prompt(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        file_dict = {"SOUL.md": "Original content"}

        mock_completion.return_value = AdaptedFilesOutput(files=[])

        refine_hatch(file_dict, minimal_egg, llm_config)

        mock_completion.assert_called_once()
        system_msg = mock_completion.call_args[1]["messages"][0]["content"]
        assert "polishing engine" in system_msg.lower()
        assert "adapt" not in system_msg.lower()

    @patch("pynydus.engine.refinement.create_completion")
    def test_failure_returns_original(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        file_dict = {"SOUL.md": "Original content"}
        mock_completion.return_value = None

        result = refine_hatch(file_dict, minimal_egg, llm_config)

        assert result["SOUL.md"] == "Original content"
        assert result is file_dict

    @patch("pynydus.engine.refinement.create_completion")
    def test_empty_files_skips(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        refine_hatch({}, minimal_egg, llm_config)
        mock_completion.assert_not_called()

    @patch("pynydus.engine.refinement.create_completion")
    def test_ignores_unknown_file_paths(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        file_dict = {"SOUL.md": "Original"}
        mock_completion.return_value = AdaptedFilesOutput(
            files=[
                AdaptedFile(path="SOUL.md", content="Adapted"),
                AdaptedFile(path="malicious.md", content="Should not appear"),
            ],
        )

        result = refine_hatch(file_dict, minimal_egg, llm_config)

        assert result["SOUL.md"] == "Adapted"
        assert "malicious.md" not in result

    @patch("pynydus.engine.refinement.create_completion")
    def test_raw_artifacts_included_in_prompt(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        file_dict = {"SOUL.md": "Reconstructed content"}
        mock_completion.return_value = AdaptedFilesOutput(files=[])

        refine_hatch(
            file_dict,
            minimal_egg,
            llm_config,
            raw_artifacts={"SOUL.md": "Original raw content"},
        )

        user_msg = mock_completion.call_args[1]["messages"][1]["content"]
        assert "Original raw content" in user_msg
        assert "raw/SOUL.md" in user_msg

    @patch("pynydus.engine.refinement.create_completion")
    def test_secrets_summary_included_in_prompt(
        self,
        mock_completion: MagicMock,
        llm_config: LLMTierConfig,
    ):
        from pynydus.api.schemas import (
            Manifest,
            SecretRecord,
            SecretsModule,
        )
        from pynydus.common.enums import (
            AgentType,
            Bucket,
            InjectionMode,
            SecretKind,
        )

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL, Bucket.MEMORY, Bucket.SECRET],
            ),
            secrets=SecretsModule(
                secrets=[
                    SecretRecord(
                        id="secret_001",
                        placeholder="{{SECRET_001}}",
                        kind=SecretKind.CREDENTIAL,
                        name="API_KEY",
                        required_at_hatch=True,
                        injection_mode=InjectionMode.ENV,
                        description="OpenAI API key",
                    ),
                ]
            ),
        )
        file_dict = {"SOUL.md": "Content"}
        mock_completion.return_value = AdaptedFilesOutput(files=[])

        refine_hatch(file_dict, egg, llm_config)

        user_msg = mock_completion.call_args[1]["messages"][1]["content"]
        assert "{{SECRET_001}}" in user_msg
        assert "API_KEY" in user_msg


# ---------------------------------------------------------------------------
# Tier selection
# ---------------------------------------------------------------------------


class TestTierSelection:
    @patch("pynydus.engine.refinement.create_completion")
    def test_spawn_memory_uses_simple_tier(
        self,
        mock_completion: MagicMock,
        sample_partial: EggPartial,
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(original_ids=[r.id], text=r.text, label=r.label)
                for r in sample_partial.memory.memory
            ]
        )

        refine_memory(sample_partial.memory, llm_config)

        first_call_tier = mock_completion.call_args[0][0]
        assert first_call_tier is llm_config

    @patch("pynydus.engine.refinement.create_completion")
    def test_hatch_uses_complex_tier(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        file_dict = {"SOUL.md": "Content"}
        mock_completion.return_value = AdaptedFilesOutput(files=[])

        refine_hatch(file_dict, minimal_egg, llm_config)

        call_tier = mock_completion.call_args[0][0]
        assert call_tier is llm_config


# ---------------------------------------------------------------------------
# Placeholder safety guardrails
# ---------------------------------------------------------------------------


class TestHatchPlaceholderRetry:
    @patch("pynydus.engine.refinement.create_completion")
    def test_retries_then_succeeds(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        """First attempt drops a placeholder. second attempt preserves it."""
        original = "Contact {{PII_001}} or use {{SECRET_001}}."
        bad = AdaptedFilesOutput(
            files=[AdaptedFile(path="USER.md", content="Contact someone or use the key.")]
        )
        good = AdaptedFilesOutput(
            files=[
                AdaptedFile(
                    path="USER.md",
                    content="Contact {{PII_001}} or use {{SECRET_001}}.",
                )
            ]
        )
        mock_completion.side_effect = [bad, good]

        result = refine_hatch({"USER.md": original}, minimal_egg, llm_config)

        assert "{{PII_001}}" in result["USER.md"]
        assert "{{SECRET_001}}" in result["USER.md"]
        assert mock_completion.call_count == 2

    @patch("pynydus.engine.refinement.create_completion")
    def test_exhausts_retries_reverts(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        """All attempts drop placeholders. original content is preserved."""
        original = "API key is {{SECRET_001}}."
        bad = AdaptedFilesOutput(
            files=[AdaptedFile(path="USER.md", content="API key is stored securely.")]
        )
        mock_completion.return_value = bad

        log: list[dict] = []
        result = refine_hatch(
            {"USER.md": original},
            minimal_egg,
            llm_config,
            log=log,
        )

        assert result["USER.md"] == original
        assert mock_completion.call_count == 3
        revert_entries = [e for e in log if e["type"] == "placeholder_revert"]
        assert len(revert_entries) == 1
        assert "{{SECRET_001}}" in revert_entries[0]["missing_placeholders"]

    @patch("pynydus.engine.refinement.create_completion")
    def test_partial_violation_keeps_good_files(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        """One file OK, one drops placeholders. only the bad one reverts."""
        files = {
            "SOUL.md": "I am helpful.",
            "USER.md": "Name: {{PII_001}}, key: {{SECRET_001}}.",
        }
        mock_completion.return_value = AdaptedFilesOutput(
            files=[
                AdaptedFile(path="SOUL.md", content="I am a helpful assistant."),
                AdaptedFile(path="USER.md", content="Name and key redacted."),
            ]
        )

        result = refine_hatch(files, minimal_egg, llm_config)

        assert result["SOUL.md"] == "I am a helpful assistant."
        assert result["USER.md"] == files["USER.md"]


class TestMemoryPlaceholderRevert:
    @patch("pynydus.engine.refinement.create_completion")
    def test_reverts_when_placeholders_dropped(
        self,
        mock_completion: MagicMock,
        llm_config: LLMTierConfig,
    ):
        original_text = "Contact {{PII_001}} at {{SECRET_001}}."
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text=original_text,
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="MEMORY.md",
                ),
            ]
        )
        mock_completion.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(
                    original_ids=["mem_001"],
                    text="Contact the user at their address.",
                    label=MemoryLabel.STATE,
                ),
            ]
        )

        result = refine_memory(memory, llm_config)

        assert result.memory[0].text == original_text


class TestSkillPlaceholderRevert:
    @patch("pynydus.engine.refinement.create_completion")
    def test_reverts_when_placeholders_dropped(
        self,
        mock_completion: MagicMock,
        llm_config: LLMTierConfig,
    ):
        original_content = "Use header Auth: {{SECRET_001}} and email {{PII_001}}."
        skills = SkillsModule(
            skills=[
                SkillRecord(
                    id="skill_001",
                    name="API helper",
                    agent_type="openclaw",
                    content=original_content,
                )
            ]
        )
        mock_completion.return_value = RefinedSkillsOutput(
            skills=[
                RefinedSkillRecord(
                    original_id="skill_001",
                    name="API Helper",
                    content="Use the authentication header and email for the account.",
                ),
            ]
        )

        result = refine_skills(skills, llm_config)

        assert result.skills[0].content == original_content
        assert result.skills[0].name == "API Helper"
