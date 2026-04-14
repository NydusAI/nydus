"""Tests for base.egg files built from recipe directories.

Uses ``./spawn.sh`` or ``uv run nydus spawn`` to build base eggs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pynydus.common.enums import AgentType, MemoryLabel
from pynydus.engine.packager import load


class TestBaseEggGeneration:
    @pytest.fixture
    def openclaw_base(self) -> Path:
        path = (
            Path(__file__).resolve().parent.parent.parent
            / "eggs"
            / "base"
            / "openclaw"
            / "0.0.1"
            / "base.egg"
        )
        if not path.exists():
            pytest.skip(
                "openclaw base.egg not built yet "
                "(from eggs/base/openclaw/0.0.1 "
                "run ./spawn.sh or: uv run nydus spawn -o ./base.egg)"
            )
        return path

    @pytest.fixture
    def zeroclaw_base(self) -> Path:
        path = (
            Path(__file__).resolve().parent.parent.parent
            / "eggs"
            / "base"
            / "zeroclaw"
            / "0.0.1"
            / "base.egg"
        )
        if not path.exists():
            pytest.skip(
                "zeroclaw base.egg not built yet (from eggs/base/zeroclaw/0.0.1 "
                "run ./spawn.sh or: uv run nydus spawn -o ./base.egg)"
            )
        return path

    @pytest.fixture
    def letta_base(self) -> Path:
        path = (
            Path(__file__).resolve().parent.parent.parent
            / "eggs"
            / "base"
            / "letta"
            / "0.0.1"
            / "base.egg"
        )
        if not path.exists():
            pytest.skip(
                "letta base.egg not built yet (from eggs/base/letta/0.0.1 run ./spawn.sh "
                "or: uv run nydus spawn -o ./base.egg)"
            )
        return path

    def test_openclaw_base_egg(self, openclaw_base: Path):
        egg = load(openclaw_base)
        assert egg.manifest.agent_type == AgentType.OPENCLAW
        assert len(egg.skills.skills) >= 2
        labels = {m.label for m in egg.memory.memory}
        assert MemoryLabel.PERSONA in labels
        assert MemoryLabel.FLOW in labels
        assert MemoryLabel.CONTEXT in labels
        assert len(egg.mcp.configs) >= 2
        assert egg.apm_yml is not None
        assert egg.a2a_card is not None
        assert egg.agents_md is not None

    def test_zeroclaw_base_egg(self, zeroclaw_base: Path):
        egg = load(zeroclaw_base)
        assert egg.manifest.agent_type == AgentType.ZEROCLAW
        assert egg.manifest.agent_name == "nydus-zeroclaw-base"
        assert egg.manifest.llm_model == "claude-3-5-sonnet"
        labels = {m.label for m in egg.memory.memory}
        assert MemoryLabel.PERSONA in labels
        assert MemoryLabel.FLOW in labels
        assert MemoryLabel.CONTEXT in labels
        assert len(egg.skills.skills) >= 1
        assert len(egg.mcp.configs) >= 2
        assert egg.apm_yml is not None
        assert egg.a2a_card is not None
        assert egg.agents_md is not None

    def test_letta_base_egg(self, letta_base: Path):
        egg = load(letta_base)
        assert egg.manifest.agent_type == AgentType.LETTA
        assert egg.manifest.agent_name == "nydus-letta-base"
        assert egg.manifest.llm_model == "gpt-4o"
        assert len(egg.memory.memory) >= 3
        labels = {m.label for m in egg.memory.memory}
        assert MemoryLabel.PERSONA in labels
        assert MemoryLabel.CONTEXT in labels
        assert MemoryLabel.FLOW in labels
        assert MemoryLabel.STATE in labels
        assert len(egg.skills.skills) >= 1
        assert len(egg.mcp.configs) >= 2
        assert egg.apm_yml is not None
        assert egg.a2a_card is not None
        assert egg.agents_md is not None
