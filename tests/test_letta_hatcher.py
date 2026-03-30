"""Tests for the Letta hatcher connector."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pynydus.agents.letta.hatcher import LettaHatcher
from pynydus.api.schemas import (
    Egg,
    HatchResult,
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
    """Create a sample Egg for Letta hatching tests."""
    return Egg(
        manifest=Manifest(
            nydus_version="0.1.0",
            created_at=datetime.now(UTC),
            source_type=SourceType.OPENCLAW,
            included_modules=["skills", "memory", "secrets"],
            source_metadata={"source_dir": "/tmp/test"},
        ),
        skills=SkillsModule(
            skills=[
                SkillRecord(
                    id="skill_001",
                    name="web search",
                    source_type="markdown_skill",
                    content="def web_search(query: str) -> str:\n    \"\"\"Search the web.\"\"\"\n    return query",
                ),
                SkillRecord(
                    id="skill_002",
                    name="calculate",
                    source_type="markdown_skill",
                    content="def calculate(expr: str) -> float:\n    return eval(expr)",
                ),
            ]
        ),
        memory=MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="You are a helpful research assistant.",
                    label=MemoryLabel.FLOW,
                    source_framework="openclaw",
                    source_store="soul.md",
                ),
                MemoryRecord(
                    id="mem_002",
                    text="I prefer concise answers and bullet points.",
                    label=MemoryLabel.PERSONA,
                    source_framework="openclaw",
                    source_store="soul.md",
                ),
                MemoryRecord(
                    id="mem_003",
                    text="The user is a data scientist at Acme Corp.",
                    label=MemoryLabel.CONTEXT,
                    source_framework="openclaw",
                    source_store="knowledge.md",
                ),
                MemoryRecord(
                    id="mem_004",
                    text="Python 3.12 added new typing features.",
                    label=MemoryLabel.STATE,
                    source_framework="openclaw",
                    source_store="knowledge.md",
                ),
                MemoryRecord(
                    id="mem_005",
                    text="Historical conversation about ML pipelines.",
                    label=MemoryLabel.STATE,
                    source_framework="letta",
                    source_store="archival_memory",
                    timestamp=datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
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
def hatcher() -> LettaHatcher:
    return LettaHatcher()


class TestHatch:
    def test_creates_agent_state(
        self, hatcher: LettaHatcher, sample_egg: Egg, tmp_path: Path
    ):
        result = hatcher.hatch(sample_egg, tmp_path)
        assert "agent_state.json" in result.files_created
        data = json.loads((tmp_path / "agent_state.json").read_text())
        assert isinstance(data, dict)
        assert "memory" in data

    def test_agent_state_has_memory_blocks(
        self, hatcher: LettaHatcher, sample_egg: Egg, tmp_path: Path
    ):
        hatcher.hatch(sample_egg, tmp_path)
        data = json.loads((tmp_path / "agent_state.json").read_text())
        # persona / user_context → Letta memory blocks
        assert "persona" in data["memory"]
        assert "human" in data["memory"]
        assert "concise" in data["memory"]["persona"]["value"]
        assert "data scientist" in data["memory"]["human"]["value"]

    def test_agent_state_has_system_prompt(
        self, hatcher: LettaHatcher, sample_egg: Egg, tmp_path: Path
    ):
        hatcher.hatch(sample_egg, tmp_path)
        data = json.loads((tmp_path / "agent_state.json").read_text())
        assert "system" in data
        assert "research assistant" in data["system"]

    def test_agent_state_has_tools(
        self, hatcher: LettaHatcher, sample_egg: Egg, tmp_path: Path
    ):
        hatcher.hatch(sample_egg, tmp_path)
        data = json.loads((tmp_path / "agent_state.json").read_text())
        assert len(data["tools"]) == 2
        names = {t["name"] for t in data["tools"]}
        assert "web_search" in names
        assert "calculate" in names

    def test_creates_system_prompt_md(
        self, hatcher: LettaHatcher, sample_egg: Egg, tmp_path: Path
    ):
        result = hatcher.hatch(sample_egg, tmp_path)
        assert "system_prompt.md" in result.files_created
        content = (tmp_path / "system_prompt.md").read_text()
        assert "research assistant" in content

    def test_creates_tools_directory(
        self, hatcher: LettaHatcher, sample_egg: Egg, tmp_path: Path
    ):
        result = hatcher.hatch(sample_egg, tmp_path)
        assert "tools/web_search.py" in result.files_created
        assert "tools/calculate.py" in result.files_created
        assert (tmp_path / "tools" / "web_search.py").exists()
        assert (tmp_path / "tools" / "calculate.py").exists()

    def test_creates_archival_memory(
        self, hatcher: LettaHatcher, sample_egg: Egg, tmp_path: Path
    ):
        result = hatcher.hatch(sample_egg, tmp_path)
        assert "archival_memory.json" in result.files_created
        data = json.loads((tmp_path / "archival_memory.json").read_text())
        assert isinstance(data, list)
        # fact + archival records go here
        texts = [e["text"] for e in data]
        assert any("ML pipelines" in t for t in texts)

    def test_creates_letta_config(
        self, hatcher: LettaHatcher, sample_egg: Egg, tmp_path: Path
    ):
        result = hatcher.hatch(sample_egg, tmp_path)
        assert ".letta/config.json" in result.files_created
        data = json.loads((tmp_path / ".letta" / "config.json").read_text())
        assert data["API_KEY"] == "{{SECRET_001}}"

    def test_empty_egg_still_produces_agent_state(
        self, hatcher: LettaHatcher, tmp_path: Path
    ):
        """Even a minimal egg should produce agent_state.json."""
        minimal_egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=[],
            ),
        )
        result = hatcher.hatch(minimal_egg, tmp_path)
        assert "agent_state.json" in result.files_created

    def test_creates_output_dir(
        self, hatcher: LettaHatcher, sample_egg: Egg, tmp_path: Path
    ):
        out = tmp_path / "nested" / "output"
        result = hatcher.hatch(sample_egg, out)
        assert out.is_dir()
        assert len(result.files_created) > 0

    def test_target_is_letta(
        self, hatcher: LettaHatcher, sample_egg: Egg, tmp_path: Path
    ):
        result = hatcher.hatch(sample_egg, tmp_path)
        assert result.target == "letta"

class TestValidate:
    def test_valid_output(
        self, hatcher: LettaHatcher, sample_egg: Egg, tmp_path: Path
    ):
        result = hatcher.hatch(sample_egg, tmp_path)
        report = hatcher.validate(result)
        assert report.valid is True

    def test_missing_file(self, hatcher: LettaHatcher, tmp_path: Path):
        result = HatchResult(
            target="letta",
            output_dir=tmp_path,
            files_created=["agent_state.json", "nonexistent.md"],
        )
        (tmp_path / "agent_state.json").write_text("{}")
        report = hatcher.validate(result)
        assert report.valid is False
        assert any("not found" in i.message for i in report.issues)

    def test_invalid_agent_state_json(self, hatcher: LettaHatcher, tmp_path: Path):
        result = HatchResult(
            target="letta",
            output_dir=tmp_path,
            files_created=["agent_state.json"],
        )
        (tmp_path / "agent_state.json").write_text("not json {{{")
        report = hatcher.validate(result)
        assert report.valid is False
