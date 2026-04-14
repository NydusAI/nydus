"""Integration test: ZeroClaw passthrough hatch preserves the original layout.

Spawns from a rich ZeroClaw source, hatches in passthrough mode, and verifies
the original file structure and content are preserved. Also compares rebuild
vs passthrough to confirm both cover the same semantic content.

Marked ``@pytest.mark.integration``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pynydus.common.enums import AgentType, HatchMode
from pynydus.engine.hatcher import hatch

from _zeroclaw_hatch_fixtures import spawn_rich_zeroclaw

pytestmark = pytest.mark.integration


class TestPassthroughLayout:
    """Passthrough hatch preserves the original file structure."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path):
        loaded, raw = spawn_rich_zeroclaw(tmp_path)
        out = tmp_path / "passthrough"
        self.result = hatch(
            loaded,
            target=AgentType.ZEROCLAW,
            output_dir=out,
            mode=HatchMode.PASSTHROUGH,
            raw_artifacts=loaded.raw_artifacts or raw,
        )
        self.out = out

    def test_uppercase_filenames_preserved(self):
        assert "agent/SOUL.md" in self.result.files_created
        assert "agent/IDENTITY.md" in self.result.files_created
        assert "AGENTS.md" in self.result.files_created
        assert "agent/USER.md" in self.result.files_created
        assert "agent/TOOLS.md" in self.result.files_created
        assert "agent/MEMORY.md" in self.result.files_created

    def test_tools_dir_preserved(self):
        assert "agent/tools/search_web.py" in self.result.files_created
        assert "agent/tools/file_read.py" in self.result.files_created

    def test_memory_dir_preserved(self):
        assert "agent/memory/2026-03-15.md" in self.result.files_created
        assert "agent/memory/2026-03-17.md" in self.result.files_created

    def test_config_toml_preserved(self):
        assert "agent/config.toml" in self.result.files_created
        content = (self.out / "agent" / "config.toml").read_text()
        assert "claude-3" in content

    def test_content_matches_source(self):
        assert "code examples" in (self.out / "agent" / "SOUL.md").read_text()
        assert "ZeroClaw Agent v2" in (self.out / "agent" / "IDENTITY.md").read_text()
        assert "epoll" in (self.out / "agent" / "memory" / "2026-03-15.md").read_text()


class TestRebuildVsPassthrough:
    """Both modes produce output covering the same semantic content."""

    def test_same_content_different_structure(self, tmp_path: Path):
        loaded, raw = spawn_rich_zeroclaw(tmp_path)

        rebuild_out = tmp_path / "rebuild"
        rebuild = hatch(loaded, target=AgentType.ZEROCLAW, output_dir=rebuild_out)

        passthrough_out = tmp_path / "passthrough"
        passthrough = hatch(
            loaded,
            target=AgentType.ZEROCLAW,
            output_dir=passthrough_out,
            mode=HatchMode.PASSTHROUGH,
            raw_artifacts=loaded.raw_artifacts or raw,
        )

        rebuild_files = set(rebuild.files_created)
        passthrough_files = set(passthrough.files_created)

        for key_file in (
            "agent/persona.md",
            "agent/agents.md",
            "agent/user.md",
            "agent/knowledge.md",
        ):
            assert key_file in rebuild_files, f"{key_file} missing from rebuild"

        for key_file in (
            "agent/SOUL.md",
            "AGENTS.md",
            "agent/USER.md",
            "agent/MEMORY.md",
        ):
            assert key_file in passthrough_files, f"{key_file} missing from passthrough"

        rebuild_all = " ".join(
            (rebuild_out / f).read_text()
            for f in rebuild.files_created
            if f.endswith((".md", ".py", ".toml")) and (rebuild_out / f).exists()
        )
        passthrough_all = " ".join(
            (passthrough_out / f).read_text()
            for f in passthrough.files_created
            if f.endswith((".md", ".py", ".toml")) and (passthrough_out / f).exists()
        )

        for keyword in (
            "ZeroClaw Agent v2",
            "Protocol",
            "rate limit",
            "Tokio",
            "epoll",
            "Benchmarked",
            "search_web",
            "file_read",
        ):
            assert keyword in rebuild_all, f"'{keyword}' missing from rebuild output"
            assert keyword in passthrough_all, f"'{keyword}' missing from passthrough output"
