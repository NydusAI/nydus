"""Integration test: ZeroClaw rebuild hatch produces the canonical workspace layout.

Spawns from a rich ZeroClaw source (all file types), hatches in rebuild mode,
and verifies every canonical file is produced with correct content routing.

Marked ``@pytest.mark.integration``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pynydus.common.enums import AgentType
from pynydus.engine.hatcher import hatch

from _zeroclaw_hatch_fixtures import spawn_rich_zeroclaw

pytestmark = pytest.mark.integration


class TestRebuildLayout:
    """Rebuild hatch produces the canonical ZeroClaw workspace layout."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path):
        loaded, _raw = spawn_rich_zeroclaw(tmp_path)
        out = tmp_path / "rebuild"
        self.result = hatch(loaded, target=AgentType.ZEROCLAW, output_dir=out)
        self.out = out

    def test_persona_present(self):
        assert "persona.md" in self.result.files_created
        content = (self.out / "persona.md").read_text()
        assert "code examples" in content

    def test_identity_present(self):
        assert "identity.md" in self.result.files_created
        content = (self.out / "identity.md").read_text()
        assert "ZeroClaw Agent v2" in content

    def test_agents_present(self):
        assert "agents.md" in self.result.files_created
        content = (self.out / "agents.md").read_text()
        assert "Protocol" in content

    def test_user_present(self):
        assert "user.md" in self.result.files_created
        content = (self.out / "user.md").read_text()
        assert "Rust" in content

    def test_tools_md_present(self):
        assert "tools.md" in self.result.files_created
        content = (self.out / "tools.md").read_text()
        assert "rate limit" in content.lower()

    def test_knowledge_undated(self):
        assert "knowledge.md" in self.result.files_created
        content = (self.out / "knowledge.md").read_text()
        assert "Tokio" in content

    def test_memory_dated_files(self):
        assert "memory/2026-03-15.md" in self.result.files_created
        assert "memory/2026-03-17.md" in self.result.files_created
        assert "epoll" in (self.out / "memory" / "2026-03-15.md").read_text()
        assert "Benchmarked" in (self.out / "memory" / "2026-03-17.md").read_text()

    def test_tools_directory(self):
        tool_files = [f for f in self.result.files_created if f.startswith("tools/")]
        assert len(tool_files) == 2
        assert "tools/search_web.py" in self.result.files_created
        assert "tools/file_read.py" in self.result.files_created

    def test_tool_content(self):
        assert "search_web" in (self.out / "tools" / "search_web.py").read_text()
        assert "file_read" in (self.out / "tools" / "file_read.py").read_text()

    def test_config_toml(self):
        assert "config.toml" in self.result.files_created
        content = (self.out / "config.toml").read_text()
        assert "zc-agent" in content
        assert "claude-3" in content

    def test_zeroclaw_marker(self):
        assert ".zeroclaw/.keep" in self.result.files_created
        assert (self.out / ".zeroclaw").is_dir()

    def test_no_uppercase_filenames(self):
        md_files = [f for f in self.result.files_created if f.endswith(".md")]
        for f in md_files:
            basename = f.split("/")[-1]
            assert basename == basename.lower(), f"Expected lowercase filename, got {f}"

    def test_no_legacy_files(self):
        for bad in ("SOUL.md", "IDENTITY.md", "AGENTS.md", "USER.md", "TOOLS.md", "MEMORY.md",
                     "config.json"):
            assert bad not in self.result.files_created, f"Legacy file {bad} should not exist"
