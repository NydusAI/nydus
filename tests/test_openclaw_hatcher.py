"""Tests for the OpenClaw hatcher connector."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pynydus.agents.openclaw.hatcher import OpenClawHatcher
from pynydus.api.errors import HatchError
from pynydus.api.schemas import (
    Egg,
    InjectionMode,
    Manifest,
    MemoryLabel,
    MemoryModule,
    MemoryRecord,
    SecretKind,
    SecretRecord,
    SecretsModule,
    SkillRecord,
    SkillsModule,
    SourceType,
)


@pytest.fixture
def sample_egg() -> Egg:
    """Create a sample Egg for hatching tests."""
    return Egg(
        manifest=Manifest(
            nydus_version="0.1.0",
            created_at=datetime.now(UTC),
            source_type=SourceType.OPENCLAW,
            included_modules=["skills", "memory", "secrets"],
        ),
        skills=SkillsModule(
            skills=[
                SkillRecord(
                    id="skill_001",
                    name="Summarize",
                    source_type="markdown_skill",
                    content="Produce a 5-bullet summary of any document.",
                ),
                SkillRecord(
                    id="skill_002",
                    name="Translate",
                    source_type="markdown_skill",
                    content="Translate between English and French.",
                ),
            ]
        ),
        memory=MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="I prefer concise answers.",
                    label=MemoryLabel.PERSONA,
                    source_framework="openclaw",
                    source_store="soul.md",
                ),
                MemoryRecord(
                    id="mem_002",
                    text="Python was created by Guido van Rossum.",
                    label=MemoryLabel.STATE,
                    source_framework="openclaw",
                    source_store="knowledge.md",
                ),
                MemoryRecord(
                    id="mem_003",
                    text="Some unlabeled context.",
                    label=MemoryLabel.STATE,
                    source_framework="letta",
                    source_store="memory_block",
                ),
            ]
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
                    description="API key",
                ),
            ]
        ),
    )


@pytest.fixture
def hatcher() -> OpenClawHatcher:
    return OpenClawHatcher()


class TestHatch:
    def test_creates_soul_md(
        self, hatcher: OpenClawHatcher, sample_egg: Egg, tmp_path: Path
    ):
        result = hatcher.hatch(sample_egg, tmp_path)
        assert "soul.md" in result.files_created
        content = (tmp_path / "soul.md").read_text()
        assert "I prefer concise answers." in content

    def test_creates_knowledge_md(
        self, hatcher: OpenClawHatcher, sample_egg: Egg, tmp_path: Path
    ):
        result = hatcher.hatch(sample_egg, tmp_path)
        assert "knowledge.md" in result.files_created
        content = (tmp_path / "knowledge.md").read_text()
        assert "Guido van Rossum" in content

    def test_creates_skill_md(
        self, hatcher: OpenClawHatcher, sample_egg: Egg, tmp_path: Path
    ):
        result = hatcher.hatch(sample_egg, tmp_path)
        assert "skill.md" in result.files_created
        content = (tmp_path / "skill.md").read_text()
        assert "# Summarize" in content
        assert "# Translate" in content

    def test_creates_config_json(
        self, hatcher: OpenClawHatcher, sample_egg: Egg, tmp_path: Path
    ):
        result = hatcher.hatch(sample_egg, tmp_path)
        assert "config.json" in result.files_created
        content = (tmp_path / "config.json").read_text()
        assert "{{SECRET_001}}" in content

    def test_knowledge_records_merge_into_knowledge_md(
        self, hatcher: OpenClawHatcher, sample_egg: Egg, tmp_path: Path
    ):
        """Former CONTEXT-style records map to KNOWLEDGE and merge into knowledge.md."""
        result = hatcher.hatch(sample_egg, tmp_path)
        assert "knowledge.md" in result.files_created
        assert "notes.md" not in result.files_created
        assert result.warnings == []
        content = (tmp_path / "knowledge.md").read_text()
        assert "Guido van Rossum" in content
        assert "unlabeled context" in content

    def test_empty_egg_raises(self, hatcher: OpenClawHatcher, tmp_path: Path):
        empty_egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=[],
            ),
        )
        with pytest.raises(HatchError, match="no output files"):
            hatcher.hatch(empty_egg, tmp_path)

    def test_creates_output_dir(
        self, hatcher: OpenClawHatcher, sample_egg: Egg, tmp_path: Path
    ):
        out = tmp_path / "nested" / "output"
        result = hatcher.hatch(sample_egg, out)
        assert out.is_dir()
        assert len(result.files_created) > 0


class TestValidate:
    def test_valid_output(
        self, hatcher: OpenClawHatcher, sample_egg: Egg, tmp_path: Path
    ):
        result = hatcher.hatch(sample_egg, tmp_path)
        report = hatcher.validate(result)
        assert report.valid is True

    def test_missing_file(self, hatcher: OpenClawHatcher, tmp_path: Path):
        from pynydus.api.schemas import HatchResult

        result = HatchResult(
            target="openclaw",
            output_dir=tmp_path,
            files_created=["soul.md", "nonexistent.md"],
        )
        (tmp_path / "soul.md").write_text("test")
        report = hatcher.validate(result)
        assert report.valid is False
