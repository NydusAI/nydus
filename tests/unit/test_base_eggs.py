"""Tests for base.egg files produced by ``make base-eggs``."""

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
            / "dist"
            / "base_eggs"
            / "openclaw"
            / "base.egg"
        )
        if not path.exists():
            pytest.skip("openclaw base.egg not generated yet (run 'make base-eggs')")
        return path

    @pytest.fixture
    def letta_base(self) -> Path:
        path = (
            Path(__file__).resolve().parent.parent.parent
            / "dist"
            / "base_eggs"
            / "letta"
            / "base.egg"
        )
        if not path.exists():
            pytest.skip("letta base.egg not generated yet (run 'make base-eggs')")
        return path

    def test_openclaw_base_egg(self, openclaw_base: Path):
        egg = load(openclaw_base)
        assert egg.manifest.agent_type == AgentType.OPENCLAW
        assert egg.manifest.egg_version == "2.0"
        assert len(egg.skills.skills) >= 1
        assert len(egg.memory.memory) >= 1
        assert egg.memory.memory[0].label == MemoryLabel.PERSONA
        assert len(egg.secrets.secrets) >= 1
        assert "OPENAI_API_KEY" in {s.name for s in egg.secrets.secrets}

    def test_letta_base_egg(self, letta_base: Path):
        egg = load(letta_base)
        assert egg.manifest.agent_type == AgentType.LETTA
        assert egg.manifest.egg_version == "2.0"
        assert len(egg.memory.memory) >= 3
        labels = {m.label for m in egg.memory.memory}
        assert MemoryLabel.PERSONA in labels
        assert MemoryLabel.CONTEXT in labels
        assert MemoryLabel.FLOW in labels
        names = {s.name for s in egg.secrets.secrets}
        assert "OPENAI_API_KEY" in names
        assert "LETTA_SERVER_URL" in names
        assert egg.manifest.source_metadata.get("kind") == "base_egg"
        assert egg.manifest.source_metadata.get("namespace") == "nydus/letta"
