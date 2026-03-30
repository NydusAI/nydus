"""Tests for LLM refinement logic (engine/refinement.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

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
            source_framework="openclaw",
            source_store="soul.md",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        MemoryRecord(
            id="mem_002",
            text="I'm a research assistant that helps with papers.",
            label=MemoryLabel.PERSONA,
            source_framework="openclaw",
            source_store="soul.md",
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        ),
        MemoryRecord(
            id="mem_003",
            text="The capital of France is Paris.",
            label=MemoryLabel.STATE,
            source_framework="openclaw",
            source_store="knowledge.md",
        ),
    ]


@pytest.fixture
def sample_skill_records() -> list[SkillRecord]:
    return [
        SkillRecord(
            id="skill_001",
            name="  summarize Documents  ",
            source_type="markdown_skill",
            content="Given a document, produce a 5-bullet summary.\n\n",
            metadata={"path": "skill.md"},
        ),
        SkillRecord(
            id="skill_002",
            name="translate_text",
            source_type="markdown_skill",
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
            files=[AdaptedFile(path="soul.md", content="Updated content")],
            warnings=["Minor formatting issue"],
        )
        assert len(output.files) == 1
        assert len(output.warnings) == 1

    def test_adapted_files_output_default_warnings(self):
        output = AdaptedFilesOutput(files=[])
        assert output.warnings == []


# ---------------------------------------------------------------------------
# refine_memory — memory deduplication
# ---------------------------------------------------------------------------


class TestRefineMemory:
    @patch("pynydus.engine.refinement.create_completion")
    def test_deduplicates_memory(
        self,
        mock_completion: MagicMock,
        sample_partial: EggPartial,
        llm_config: NydusLLMConfig,
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
        assert merged.source_framework == "openclaw"
        assert merged.source_store == "soul.md"
        fact = result.memory[1]
        assert fact.id == "mem_003"

    @patch("pynydus.engine.refinement.create_completion")
    def test_failure_returns_original(
        self,
        mock_completion: MagicMock,
        sample_partial: EggPartial,
        llm_config: NydusLLMConfig,
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
        llm_config: NydusLLMConfig,
    ):
        result = refine_memory(MemoryModule(memory=[]), llm_config)
        assert result.memory == []

    @patch("pynydus.engine.refinement.create_completion")
    def test_preserves_placeholder_tokens(
        self,
        mock_completion: MagicMock,
        llm_config: NydusLLMConfig,
    ):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="Contact {{PII_001}} at {{PII_002}}.",
                    label=MemoryLabel.STATE,
                    source_framework="openclaw",
                    source_store="knowledge.md",
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
# refine_skills — skill cleanup
# ---------------------------------------------------------------------------


class TestRefineSkills:
    @patch("pynydus.engine.refinement.create_completion")
    def test_cleans_skills(
        self,
        mock_completion: MagicMock,
        sample_partial: EggPartial,
        llm_config: NydusLLMConfig,
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
        assert result.skills[0].source_type == "markdown_skill"
        assert result.skills[0].metadata == {"path": "skill.md"}

    @patch("pynydus.engine.refinement.create_completion")
    def test_skill_failure_returns_original(
        self,
        mock_completion: MagicMock,
        llm_config: NydusLLMConfig,
    ):
        skills = SkillsModule(
            skills=[
                SkillRecord(
                    id="skill_001",
                    name="test",
                    source_type="markdown_skill",
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
        llm_config: NydusLLMConfig,
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
        llm_config: NydusLLMConfig,
    ):
        file_dict = {"soul.md": "Original soul content", "skill.md": "Original skill content"}

        mock_completion.return_value = AdaptedFilesOutput(
            files=[
                AdaptedFile(path="soul.md", content="Adapted soul content for Letta"),
            ],
        )

        result = refine_hatch(file_dict, minimal_egg, llm_config)

        assert result["soul.md"] == "Adapted soul content for Letta"
        assert result["skill.md"] == "Original skill content"

    @patch("pynydus.engine.refinement.create_completion")
    def test_same_platform_uses_polish_prompt(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: NydusLLMConfig,
    ):
        file_dict = {"soul.md": "Original content"}

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
        llm_config: NydusLLMConfig,
    ):
        file_dict = {"soul.md": "Original content"}
        mock_completion.return_value = None

        result = refine_hatch(file_dict, minimal_egg, llm_config)

        assert result["soul.md"] == "Original content"
        assert result is file_dict

    @patch("pynydus.engine.refinement.create_completion")
    def test_empty_files_skips(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: NydusLLMConfig,
    ):
        refine_hatch({}, minimal_egg, llm_config)
        mock_completion.assert_not_called()

    @patch("pynydus.engine.refinement.create_completion")
    def test_ignores_unknown_file_paths(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: NydusLLMConfig,
    ):
        file_dict = {"soul.md": "Original"}
        mock_completion.return_value = AdaptedFilesOutput(
            files=[
                AdaptedFile(path="soul.md", content="Adapted"),
                AdaptedFile(path="malicious.md", content="Should not appear"),
            ],
        )

        result = refine_hatch(file_dict, minimal_egg, llm_config)

        assert result["soul.md"] == "Adapted"
        assert "malicious.md" not in result

    @patch("pynydus.engine.refinement.create_completion")
    def test_raw_artifacts_included_in_prompt(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: NydusLLMConfig,
    ):
        file_dict = {"soul.md": "Reconstructed content"}
        mock_completion.return_value = AdaptedFilesOutput(files=[])

        refine_hatch(
            file_dict, minimal_egg, llm_config,
            raw_artifacts={"soul.md": "Original raw content"},
        )

        user_msg = mock_completion.call_args[1]["messages"][1]["content"]
        assert "Original raw content" in user_msg
        assert "raw/soul.md" in user_msg

    @patch("pynydus.engine.refinement.create_completion")
    def test_secrets_summary_included_in_prompt(
        self,
        mock_completion: MagicMock,
        llm_config: NydusLLMConfig,
    ):
        from pynydus.api.schemas import (
            InjectionMode,
            Manifest,
            SecretKind,
            SecretRecord,
            SecretsModule,
            SourceType,
        )

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["skills", "memory", "secrets"],
            ),
            secrets=SecretsModule(secrets=[
                SecretRecord(
                    id="secret_001",
                    placeholder="{{SECRET_001}}",
                    kind=SecretKind.CREDENTIAL,
                    name="API_KEY",
                    required_at_hatch=True,
                    injection_mode=InjectionMode.ENV,
                    description="OpenAI API key",
                ),
            ]),
        )
        file_dict = {"soul.md": "Content"}
        mock_completion.return_value = AdaptedFilesOutput(files=[])

        refine_hatch(file_dict, egg, llm_config)

        user_msg = mock_completion.call_args[1]["messages"][1]["content"]
        assert "{{SECRET_001}}" in user_msg
        assert "API_KEY" in user_msg


# ---------------------------------------------------------------------------
# Pass-through hatch with raw artifacts
# ---------------------------------------------------------------------------


class TestPassThroughHatch:
    def test_pass_through_writes_raw_files(self, tmp_path: Path):
        from pynydus.api.schemas import Manifest, SourceType
        from pynydus.engine.hatcher import hatch

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["skills", "memory"],
            ),
        )
        raw = {"soul.md": "I am a soul.", "knowledge.md": "Facts here."}
        out = tmp_path / "output"

        result = hatch(egg, target="openclaw", output_dir=out, raw_artifacts=raw)

        assert "soul.md" in result.files_created
        assert "knowledge.md" in result.files_created
        assert (out / "soul.md").read_text() == "I am a soul."
        assert (out / "knowledge.md").read_text() == "Facts here."
        assert any(e.get("type") == "pass_through" for e in result.hatch_log)

    def test_pass_through_without_raw_falls_back_to_connector(self, tmp_path: Path):
        from pynydus.api.schemas import (
            Manifest,
            MemoryLabel,
            MemoryModule,
            MemoryRecord,
            SkillRecord,
            SkillsModule,
            SourceType,
        )
        from pynydus.engine.hatcher import hatch

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["skills", "memory"],
            ),
            skills=SkillsModule(skills=[
                SkillRecord(id="s1", name="Test", source_type="openclaw", content="Do it."),
            ]),
            memory=MemoryModule(memory=[
                MemoryRecord(
                    id="m1", text="A preference.", label=MemoryLabel.PERSONA,
                    source_framework="openclaw", source_store="soul.md",
                ),
            ]),
        )
        out = tmp_path / "output"

        result = hatch(egg, target="openclaw", output_dir=out, raw_artifacts=None)

        assert "soul.md" in result.files_created
        assert "skill.md" in result.files_created

    def test_reconstruct_flag_disables_pass_through(self, tmp_path: Path):
        from pynydus.api.schemas import (
            Manifest,
            MemoryLabel,
            MemoryModule,
            MemoryRecord,
            SkillRecord,
            SkillsModule,
            SourceType,
        )
        from pynydus.engine.hatcher import hatch

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["skills", "memory"],
            ),
            skills=SkillsModule(skills=[
                SkillRecord(id="s1", name="Test", source_type="openclaw", content="Do it."),
            ]),
            memory=MemoryModule(memory=[
                MemoryRecord(
                    id="m1", text="A preference.", label=MemoryLabel.PERSONA,
                    source_framework="openclaw", source_store="soul.md",
                ),
            ]),
        )
        raw = {"soul.md": "Raw soul content."}
        out = tmp_path / "output"

        result = hatch(
            egg, target="openclaw", output_dir=out,
            raw_artifacts=raw, reconstruct=True,
        )

        # reconstruct=True forces connector.hatch(), not raw pass-through
        assert "skill.md" in result.files_created
        # Raw content should NOT be what's in soul.md — connector rebuilds it
        soul_content = (out / "soul.md").read_text()
        assert soul_content.strip() != "Raw soul content."

    @patch("pynydus.engine.refinement.create_completion")
    def test_llm_runs_in_pass_through_mode(
        self,
        mock_completion: MagicMock,
        tmp_path: Path,
        llm_config: NydusLLMConfig,
    ):
        from pynydus.api.schemas import Manifest, SourceType
        from pynydus.engine.hatcher import hatch

        mock_completion.return_value = AdaptedFilesOutput(files=[])

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["skills", "memory"],
            ),
        )
        raw = {"soul.md": "I am a soul."}
        out = tmp_path / "output"

        hatch(
            egg, target="openclaw", output_dir=out,
            raw_artifacts=raw, llm_config=llm_config,
        )

        mock_completion.assert_called_once()
        system_msg = mock_completion.call_args[1]["messages"][0]["content"]
        assert "polishing engine" in system_msg.lower()


# ---------------------------------------------------------------------------
# Tier selection
# ---------------------------------------------------------------------------


class TestTierSelection:
    @patch("pynydus.engine.refinement.create_completion")
    def test_spawn_memory_uses_simple_tier(
        self,
        mock_completion: MagicMock,
        sample_partial: EggPartial,
        llm_config: NydusLLMConfig,
    ):
        mock_completion.return_value = RefinedMemoryOutput(
            records=[
                RefinedMemoryRecord(original_ids=[r.id], text=r.text, label=r.label)
                for r in sample_partial.memory.memory
            ]
        )

        refine_memory(sample_partial.memory, llm_config)

        first_call_tier = mock_completion.call_args[0][0]
        assert first_call_tier is llm_config.simple

    @patch("pynydus.engine.refinement.create_completion")
    def test_hatch_uses_complex_tier(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: NydusLLMConfig,
    ):
        file_dict = {"soul.md": "Content"}
        mock_completion.return_value = AdaptedFilesOutput(files=[])

        refine_hatch(file_dict, minimal_egg, llm_config)

        call_tier = mock_completion.call_args[0][0]
        assert call_tier is llm_config.complex
