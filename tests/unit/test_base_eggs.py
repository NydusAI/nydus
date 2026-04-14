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
            / "pynydus"
            / "eggs"
            / "base"
            / "openclaw"
            / "0.0.1"
            / "base.egg"
        )
        if not path.exists():
            pytest.skip(
                "openclaw base.egg not built yet "
                "(from pynydus/eggs/base/openclaw/0.0.1 "
                "run ./spawn.sh or: uv run nydus spawn -o ./base.egg)"
            )
        return path

    @pytest.fixture
    def letta_base(self) -> Path:
        path = (
            Path(__file__).resolve().parent.parent.parent
            / "pynydus"
            / "eggs"
            / "base"
            / "letta"
            / "0.0.1"
            / "base.egg"
        )
        if not path.exists():
            pytest.skip(
                "letta base.egg not built yet (from pynydus/eggs/base/letta/0.0.1 run ./spawn.sh "
                "or: uv run nydus spawn -o ./base.egg)"
            )
        return path

    def test_openclaw_base_egg(self, openclaw_base: Path):
        egg = load(openclaw_base)
        assert egg.manifest.agent_type == AgentType.OPENCLAW
        assert len(egg.skills.skills) >= 1
        assert len(egg.memory.memory) >= 1
        assert egg.memory.memory[0].label == MemoryLabel.PERSONA
        secret_names = {s.name for s in egg.secrets.secrets}
        if secret_names:
            assert "OPENAI_API_KEY" in secret_names
        else:
            assert "OPENAI_API_KEY" in egg.raw_artifacts.get("config.json", "")

    def test_letta_base_egg(self, letta_base: Path):
        egg = load(letta_base)
        assert egg.manifest.agent_type == AgentType.LETTA
        assert len(egg.memory.memory) >= 3
        labels = {m.label for m in egg.memory.memory}
        assert MemoryLabel.PERSONA in labels
        assert MemoryLabel.CONTEXT in labels
        assert MemoryLabel.FLOW in labels
        names = {s.name for s in egg.secrets.secrets}
        if names:
            assert "OPENAI_API_KEY" in names
            assert "LETTA_SERVER_URL" in names
        else:
            state = egg.raw_artifacts.get("agent_state.json", "")
            assert "OPENAI_API_KEY" in state
            assert "LETTA_SERVER_URL" in state
