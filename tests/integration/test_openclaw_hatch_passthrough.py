"""Integration test: OpenClaw passthrough hatch preserves the original layout.

Spawns from a rich OpenClaw source, hatches in passthrough mode, and verifies
the original file structure and content are preserved. Also compares rebuild
vs passthrough to confirm both cover the same semantic content.

Marked ``@pytest.mark.integration``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pynydus.common.enums import AgentType, HatchMode
from pynydus.engine.hatcher import hatch

from _openclaw_hatch_fixtures import spawn_rich_openclaw

pytestmark = pytest.mark.integration


class TestPassthroughLayout:
    """Passthrough hatch preserves the original file structure byte-for-byte."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path):
        loaded, raw = spawn_rich_openclaw(tmp_path)
        out = tmp_path / "passthrough"
        self.result = hatch(
            loaded,
            target=AgentType.OPENCLAW,
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

    def test_skills_dir_preserved(self):
        assert "agent/skills/book-flight.md" in self.result.files_created
        assert "agent/skills/search-hotels.md" in self.result.files_created

    def test_memory_dir_preserved(self):
        assert "agent/memory/2026-04-01.md" in self.result.files_created
        assert "agent/memory/2026-04-03.md" in self.result.files_created

    def test_content_matches_source(self):
        assert "no filler" in (self.out / "agent" / "SOUL.md").read_text()
        assert "Voyager" in (self.out / "agent" / "IDENTITY.md").read_text()
        assert "nonstop" in (self.out / "agent" / "memory" / "2026-04-01.md").read_text()


class TestRebuildVsPassthrough:
    """Both modes produce output covering the same semantic content."""

    def test_same_content_different_structure(self, tmp_path: Path):
        loaded, raw = spawn_rich_openclaw(tmp_path)

        rebuild_out = tmp_path / "rebuild"
        rebuild = hatch(loaded, target=AgentType.OPENCLAW, output_dir=rebuild_out)

        passthrough_out = tmp_path / "passthrough"
        passthrough = hatch(
            loaded,
            target=AgentType.OPENCLAW,
            output_dir=passthrough_out,
            mode=HatchMode.PASSTHROUGH,
            raw_artifacts=loaded.raw_artifacts or raw,
        )

        rebuild_files = set(rebuild.files_created)
        passthrough_files = set(passthrough.files_created)

        for key_file in (
            "agent/SOUL.md",
            "AGENTS.md",
            "agent/USER.md",
            "agent/MEMORY.md",
        ):
            assert key_file in rebuild_files, f"{key_file} missing from rebuild"
            assert key_file in passthrough_files, f"{key_file} missing from passthrough"

        rebuild_all = " ".join(
            (rebuild_out / f).read_text()
            for f in rebuild.files_created
            if f.endswith(".md") and (rebuild_out / f).exists()
        )
        passthrough_all = " ".join(
            (passthrough_out / f).read_text()
            for f in passthrough.files_created
            if f.endswith(".md") and (passthrough_out / f).exists()
        )

        for keyword in (
            "Voyager",
            "Protocol",
            "Flight search",
            "gold plus",
            "nonstop",
            "confirmation",
        ):
            assert keyword in rebuild_all, f"'{keyword}' missing from rebuild output"
            assert keyword in passthrough_all, f"'{keyword}' missing from passthrough output"
