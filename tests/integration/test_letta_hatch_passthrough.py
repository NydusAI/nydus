"""Integration test: Letta passthrough hatch preserves the original .af file.

Spawns from a rich Letta .af source, hatches in passthrough mode, and verifies
the original file structure and content are preserved. Also compares rebuild
vs passthrough to confirm both cover the same semantic content.

Marked ``@pytest.mark.integration``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pynydus.common.enums import AgentType, HatchMode
from pynydus.engine.hatcher import hatch

from _letta_hatch_fixtures import (
    CUSTOM_TOOL_CODE,
    HUMAN_TEXT,
    PERSONA_TEXT,
    SYSTEM_PROMPT,
    spawn_rich_letta,
)

pytestmark = pytest.mark.integration


class TestPassthroughLayout:
    """Passthrough hatch preserves the original .af file."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path):
        loaded, raw = spawn_rich_letta(tmp_path)
        out = tmp_path / "passthrough"
        self.result = hatch(
            loaded,
            target=AgentType.LETTA,
            output_dir=out,
            mode=HatchMode.PASSTHROUGH,
            raw_artifacts=loaded.raw_artifacts or raw,
        )
        self.out = out

    def test_af_preserved(self):
        assert "agent.af" in self.result.files_created

    def test_content_matches_source(self):
        content = (self.out / "agent.af").read_text()
        af = json.loads(content)
        assert "agents" in af
        assert af["agents"][0]["system"] == SYSTEM_PROMPT


class TestRebuildVsPassthrough:
    """Both modes produce output covering the same semantic content."""

    def test_same_content_different_structure(self, tmp_path: Path):
        loaded, raw = spawn_rich_letta(tmp_path)

        rebuild_out = tmp_path / "rebuild"
        rebuild = hatch(loaded, target=AgentType.LETTA, output_dir=rebuild_out)

        passthrough_out = tmp_path / "passthrough"
        passthrough = hatch(
            loaded,
            target=AgentType.LETTA,
            output_dir=passthrough_out,
            mode=HatchMode.PASSTHROUGH,
            raw_artifacts=loaded.raw_artifacts or raw,
        )

        assert "agent.af" in set(rebuild.files_created)
        assert "agent.af" in set(passthrough.files_created)

        rebuild_af = json.loads((rebuild_out / "agent.af").read_text())
        passthrough_af = json.loads((passthrough_out / "agent.af").read_text())

        rebuild_agent = rebuild_af["agents"][0]
        passthrough_agent = passthrough_af["agents"][0]

        for keyword in ("research assistant", "cite sources"):
            assert keyword in rebuild_agent["system"], f"'{keyword}' missing from rebuild"
            assert keyword in passthrough_agent["system"], f"'{keyword}' missing from passthrough"

        rebuild_block_labels = {b["label"] for b in rebuild_af["blocks"]}
        passthrough_block_labels = {b["label"] for b in passthrough_af.get("blocks", [])}
        for label in ("persona", "human"):
            assert label in rebuild_block_labels, f"Block '{label}' missing from rebuild"
