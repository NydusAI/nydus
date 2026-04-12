"""Integration test: Letta rebuild hatch produces a valid .af AgentFile.

Spawns from a rich Letta .af source, hatches in rebuild mode, and verifies
the output is a single agent.af conforming to AgentFileSchema.

Marked ``@pytest.mark.integration``: requires ``gitleaks`` on PATH.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pynydus.common.enums import AgentType
from pynydus.engine.hatcher import hatch

from _letta_hatch_fixtures import (
    spawn_rich_letta,
)

pytestmark = pytest.mark.integration


class TestRebuildLayout:
    """Rebuild hatch produces a valid .af AgentFile."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path):
        loaded, _raw = spawn_rich_letta(tmp_path)
        out = tmp_path / "rebuild"
        self.result = hatch(loaded, target=AgentType.LETTA, output_dir=out)
        self.out = out
        self.af = json.loads((out / "agent.af").read_text())

    def test_af_present(self):
        assert "agent.af" in self.result.files_created

    def test_af_has_agents(self):
        assert "agents" in self.af
        assert len(self.af["agents"]) == 1

    def test_af_has_blocks(self):
        assert "blocks" in self.af
        assert len(self.af["blocks"]) >= 2

    def test_af_has_tools(self):
        assert "tools" in self.af
        assert len(self.af["tools"]) >= 1

    def test_persona_block(self):
        persona_blocks = [b for b in self.af["blocks"] if b["label"] == "persona"]
        assert len(persona_blocks) == 1
        assert "machine learning" in persona_blocks[0]["value"]

    def test_human_block(self):
        human_blocks = [b for b in self.af["blocks"] if b["label"] == "human"]
        assert len(human_blocks) == 1
        assert "PhD student" in human_blocks[0]["value"]

    def test_system_prompt_in_agent(self):
        agent = self.af["agents"][0]
        assert "research assistant" in agent["system"]

    def test_custom_tool_present(self):
        custom = [t for t in self.af["tools"] if t.get("tool_type") == "custom"]
        assert len(custom) >= 1
        assert any("search_papers" in t["name"] for t in custom)

    def test_custom_tool_has_source(self):
        custom = [t for t in self.af["tools"] if t.get("tool_type") == "custom"]
        for tool in custom:
            assert tool["source_code"] is not None

    def test_block_ids_reference_blocks(self):
        agent = self.af["agents"][0]
        block_ids_in_af = {b["id"] for b in self.af["blocks"]}
        for bid in agent["block_ids"]:
            assert bid in block_ids_in_af

    def test_tool_ids_reference_tools(self):
        agent = self.af["agents"][0]
        tool_ids_in_af = {t["id"] for t in self.af["tools"]}
        for tid in agent["tool_ids"]:
            assert tid in tool_ids_in_af

    def test_metadata_present(self):
        assert "metadata" in self.af
        assert self.af["metadata"]["nydus_source"] == "letta"

    def test_no_legacy_files(self):
        for bad in ("agent_state.json", "system_prompt.md", ".letta/config.json"):
            assert bad not in self.result.files_created, f"Legacy file {bad} should not exist"
        assert not any(f.startswith("tools/") for f in self.result.files_created)

    def test_valid_json(self):
        content = (self.out / "agent.af").read_text()
        parsed = json.loads(content)
        assert isinstance(parsed, dict)
        assert "agents" in parsed
