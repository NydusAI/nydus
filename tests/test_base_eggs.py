"""Tests for base.egg files produced by ``make base-eggs``."""

from __future__ import annotations

from pathlib import Path

import pytest

from pynydus.api.schemas import MemoryLabel, SourceType
from pynydus.engine.packager import unpack


class TestBaseEggGeneration:
    """Verify the generated base.egg files are valid and contain expected data."""

    @pytest.fixture
    def openclaw_base(self) -> Path:
        path = Path(__file__).resolve().parent.parent / "dist" / "base_eggs" / "openclaw" / "base.egg"
        if not path.exists():
            pytest.skip("openclaw base.egg not generated yet (run 'make base-eggs')")
        return path

    @pytest.fixture
    def letta_base(self) -> Path:
        path = Path(__file__).resolve().parent.parent / "dist" / "base_eggs" / "letta" / "base.egg"
        if not path.exists():
            pytest.skip("letta base.egg not generated yet (run 'make base-eggs')")
        return path

    def test_openclaw_base_unpacks(self, openclaw_base: Path):
        egg = unpack(openclaw_base)
        assert egg.manifest.source_type == SourceType.OPENCLAW
        assert egg.manifest.egg_version == "2.0"

    def test_openclaw_base_has_skill(self, openclaw_base: Path):
        egg = unpack(openclaw_base)
        assert len(egg.skills.skills) >= 1

    def test_openclaw_base_has_memory(self, openclaw_base: Path):
        egg = unpack(openclaw_base)
        assert len(egg.memory.memory) >= 1
        assert egg.memory.memory[0].label == MemoryLabel.PERSONA

    def test_openclaw_base_has_secret_placeholder(self, openclaw_base: Path):
        egg = unpack(openclaw_base)
        assert len(egg.secrets.secrets) >= 1
        names = {s.name for s in egg.secrets.secrets}
        assert "OPENAI_API_KEY" in names

    def test_letta_base_unpacks(self, letta_base: Path):
        egg = unpack(letta_base)
        assert egg.manifest.source_type == SourceType.LETTA
        assert egg.manifest.egg_version == "2.0"

    def test_letta_base_has_memory_blocks(self, letta_base: Path):
        egg = unpack(letta_base)
        assert len(egg.memory.memory) >= 3
        labels = {m.label for m in egg.memory.memory}
        assert MemoryLabel.PERSONA in labels
        assert MemoryLabel.CONTEXT in labels
        assert MemoryLabel.FLOW in labels

    def test_letta_base_has_secret_placeholders(self, letta_base: Path):
        egg = unpack(letta_base)
        names = {s.name for s in egg.secrets.secrets}
        assert "OPENAI_API_KEY" in names
        assert "LETTA_SERVER_URL" in names

    def test_letta_base_metadata(self, letta_base: Path):
        egg = unpack(letta_base)
        assert egg.manifest.source_metadata.get("kind") == "base_egg"
        assert egg.manifest.source_metadata.get("namespace") == "nydus/letta"


