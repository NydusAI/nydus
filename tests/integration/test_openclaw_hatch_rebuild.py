"""Integration test: OpenClaw rebuild hatch produces the canonical workspace layout.

Spawns from a rich OpenClaw source (all file types), hatches in rebuild mode,
and verifies every canonical file is produced with correct content routing.

Marked ``@pytest.mark.integration``: requires ``gitleaks`` on PATH.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pynydus.common.enums import AgentType
from pynydus.engine.hatcher import hatch
from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective
from pynydus.engine.packager import load, save
from pynydus.engine.pipeline import spawn

from _openclaw_hatch_fixtures import spawn_rich_openclaw

pytestmark = pytest.mark.integration


class TestRebuildLayout:
    """Rebuild hatch produces the canonical OpenClaw workspace layout."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path):
        loaded, _raw = spawn_rich_openclaw(tmp_path)
        out = tmp_path / "rebuild"
        self.result = hatch(loaded, target=AgentType.OPENCLAW, output_dir=out)
        self.out = out

    def test_soul_present(self):
        assert "agent/SOUL.md" in self.result.files_created
        content = (self.out / "agent" / "SOUL.md").read_text()
        assert "no filler" in content

    def test_identity_present(self):
        assert "agent/IDENTITY.md" in self.result.files_created
        content = (self.out / "agent" / "IDENTITY.md").read_text()
        assert "Voyager" in content

    def test_agents_present(self):
        assert "AGENTS.md" in self.result.files_created
        assert "agent/AGENTS.md" in self.result.files_created
        content = (self.out / "agent" / "AGENTS.md").read_text()
        assert "Protocol" in content

    def test_user_present(self):
        assert "agent/USER.md" in self.result.files_created
        content = (self.out / "agent" / "USER.md").read_text()
        assert "window seat" in content

    def test_tools_present(self):
        assert "agent/TOOLS.md" in self.result.files_created
        content = (self.out / "agent" / "TOOLS.md").read_text()
        assert "Flight search" in content

    def test_memory_undated(self):
        assert "agent/MEMORY.md" in self.result.files_created
        content = (self.out / "agent" / "MEMORY.md").read_text()
        assert "gold plus" in content

    def test_memory_dated_files(self):
        assert "agent/memory/2026-04-01.md" in self.result.files_created
        assert "agent/memory/2026-04-03.md" in self.result.files_created
        assert "nonstop" in (self.out / "agent" / "memory" / "2026-04-01.md").read_text()
        assert "confirmation" in (self.out / "agent" / "memory" / "2026-04-03.md").read_text()

    def test_skills_directory(self):
        skill_files = [f for f in self.result.files_created if f.startswith("agent/skills/")]
        assert len(skill_files) == 2
        assert "agent/skills/book-flight.md" in self.result.files_created
        assert "agent/skills/search-hotels.md" in self.result.files_created

    def test_skill_content(self):
        assert "origin" in (self.out / "agent" / "skills" / "book-flight.md").read_text()
        assert "hotels" in (self.out / "agent" / "skills" / "search-hotels.md").read_text()

    def test_no_legacy_files(self):
        for bad in ("soul.md", "agents.md", "user.md", "knowledge.md", "skill.md"):
            assert bad not in self.result.files_created, f"Legacy file {bad} should not exist"


class TestConfigJsonRoundTrip:
    """config.json containing credential placeholders survives spawn-to-hatch."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "SOUL.md").write_text("Be helpful.\n")
        (src / "config.json").write_text(
            json.dumps(
                {
                    "OPENAI_API_KEY": (
                        "sk-proj-K8mX2pL9qR4wN7vJ3hF6dC1bY0tG5sE8aZ2xP4nM6kQ9rW1jD3fH7yB"
                    ),
                    "model": "gpt-4o",
                },
                indent=2,
            )
            + "\n"
        )

        config = NydusfileConfig(
            sources=[SourceDirective(agent_type="openclaw", path=str(src))],
            redact=True,
        )
        egg, raw_artifacts, logs = spawn(config, nydusfile_dir=tmp_path)
        egg_path = tmp_path / "test.egg"
        save(egg, egg_path, raw_artifacts=raw_artifacts, spawn_log=logs.get("spawn_log"))
        loaded = load(egg_path, include_raw=True)

        out = tmp_path / "rebuild"
        self.result = hatch(loaded, target=AgentType.OPENCLAW, output_dir=out)
        self.out = out

    def test_config_json_present(self):
        assert "agent/config.json" in self.result.files_created

    def test_config_json_has_placeholder(self):
        content = (self.out / "agent" / "config.json").read_text()
        parsed = json.loads(content)
        values = list(parsed.values())
        assert any(v.startswith("{{SECRET_") for v in values), (
            "config.json should contain a {{SECRET_NNN}} placeholder"
        )

    def test_config_json_no_raw_key(self):
        content = (self.out / "agent" / "config.json").read_text()
        assert "sk-proj-" not in content, "Raw API key must not appear in hatched config.json"
