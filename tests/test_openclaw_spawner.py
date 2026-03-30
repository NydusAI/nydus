"""Tests for the OpenClaw spawner connector."""

import json
from pathlib import Path

import pytest

from pynydus.api.errors import ConnectorError
from pynydus.api.schemas import MemoryLabel
from pynydus.agents.openclaw.spawner import OpenClawSpawner


@pytest.fixture
def spawner() -> OpenClawSpawner:
    return OpenClawSpawner()


@pytest.fixture
def openclaw_files() -> dict[str, str]:
    """Minimal OpenClaw file dict for parse() testing."""
    return {
        "soul.md": (
            "I am a research assistant.\n\n"
            "I prefer concise summaries.\n\n"
            "Contact: alex@example.com\n"
        ),
        "knowledge.md": (
            "# Domain Knowledge\n\n"
            "The speed of light is 299,792,458 m/s.\n\n"
            "Python 3.12 was released in October 2023.\n"
        ),
        "skill.md": (
            "# Summarize Documents\n\n"
            "Produce a 5-bullet summary of any document.\n\n"
            "# Data Analysis\n\n"
            "Process CSV data and generate statistical summaries.\n"
        ),
        "config.json": json.dumps({"api_key": "sk-secret-key-123", "model": "gpt-4"}),
    }


class TestDetect:
    def test_detects_with_soul(self, spawner: OpenClawSpawner, tmp_path: Path):
        (tmp_path / "soul.md").write_text("hello")
        assert spawner.detect(tmp_path) is True

    def test_detects_with_skill(self, spawner: OpenClawSpawner, tmp_path: Path):
        (tmp_path / "skill.md").write_text("hello")
        assert spawner.detect(tmp_path) is True

    def test_detects_with_skills_dir(self, spawner: OpenClawSpawner, tmp_path: Path):
        (tmp_path / "skills").mkdir()
        (tmp_path / "skills" / "search.md").write_text("search skill")
        assert spawner.detect(tmp_path) is True

    def test_rejects_empty_dir(self, spawner: OpenClawSpawner, tmp_path: Path):
        assert spawner.detect(tmp_path) is False

    def test_rejects_file(self, spawner: OpenClawSpawner, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("not a dir")
        assert spawner.detect(f) is False


class TestParse:
    def test_extracts_skills(self, spawner: OpenClawSpawner, openclaw_files: dict[str, str]):
        result = spawner.parse(openclaw_files)
        assert len(result.skills) == 2
        assert result.skills[0].name == "Summarize Documents"
        assert result.skills[1].name == "Data Analysis"

    def test_extracts_memory_with_labels(
        self, spawner: OpenClawSpawner, openclaw_files: dict[str, str]
    ):
        result = spawner.parse(openclaw_files)
        labels = {m.label for m in result.memory}
        assert MemoryLabel.PERSONA in labels
        assert MemoryLabel.STATE in labels

        prefs = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert len(prefs) == 3

        facts = [m for m in result.memory if m.label == MemoryLabel.STATE]
        assert len(facts) == 3

    def test_skills_dir(self, spawner: OpenClawSpawner):
        files = {
            "soul.md": "I am an agent.",
            "skills/search.md": "Search the web.",
            "skills/calculate.md": "Do math.",
        }
        result = spawner.parse(files)
        assert len(result.skills) == 2
        names = {s.name for s in result.skills}
        assert "search" in names
        assert "calculate" in names


class TestValidate:
    def test_valid_project(self, spawner: OpenClawSpawner, openclaw_project: Path):
        report = spawner.validate(openclaw_project)
        assert report.valid is True

    def test_empty_dir_warning(self, spawner: OpenClawSpawner, tmp_path: Path):
        report = spawner.validate(tmp_path)
        assert report.valid is True
        assert len(report.issues) == 1
        assert report.issues[0].level == "warning"

    def test_not_a_dir(self, spawner: OpenClawSpawner, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("hello")
        report = spawner.validate(f)
        assert report.valid is False
