"""Tests for connector dispatch and spawner-assigned memory labels.

Tests spawner dispatch via _get_spawner, canonical :class:`MemoryLabel` values
from spawners, and hatcher dispatch via agents/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pynydus.api.errors import ConnectorError
from pynydus.api.schemas import MemoryLabel, SourceType
from pynydus.engine.hatcher import _get_hatcher
from pynydus.engine.pipeline import _get_spawner

# ---------------------------------------------------------------------------
# Dynamic dispatch
# ---------------------------------------------------------------------------


class TestSpawnerDispatch:
    """Test that _get_spawner resolves source spawners."""

    def test_openclaw_source(self) -> None:
        spawner = _get_spawner(SourceType.OPENCLAW)
        assert hasattr(spawner, "parse")
        assert hasattr(spawner, "detect")
        assert hasattr(spawner, "validate")

    def test_letta_source(self) -> None:
        spawner = _get_spawner(SourceType.LETTA)
        assert hasattr(spawner, "parse")
        assert hasattr(spawner, "detect")

class TestHatcherDispatch:
    """Test that _get_hatcher resolves target hatchers."""

    def test_openclaw_hatcher(self) -> None:
        hatcher = _get_hatcher("openclaw")
        assert hasattr(hatcher, "hatch")
        assert hasattr(hatcher, "render")

    def test_letta_hatcher(self) -> None:
        hatcher = _get_hatcher("letta")
        assert hasattr(hatcher, "hatch")
        assert hasattr(hatcher, "render")

    def test_unknown_target_raises(self) -> None:
        with pytest.raises(ConnectorError):
            _get_hatcher("nonexistent_platform")


# ---------------------------------------------------------------------------
# Cross-platform label assignment (via spawner.parse)
# ---------------------------------------------------------------------------


class TestCrossPlatformLabels:
    """Test that spawners attach canonical MemoryLabel values to records."""

    def test_openclaw_parse_has_labels(self, tmp_path: Path) -> None:
        """OpenClaw parse produces labelled memory records."""
        files = {
            "soul.md": "I like cats\n\nI prefer mornings",
            "knowledge.md": "The sky is blue",
            "skill.md": "# Greet\n\nSay hello to the user",
        }
        spawner = _get_spawner(SourceType.OPENCLAW)
        result = spawner.parse(files)

        labels = {r.label for r in result.memory}
        assert MemoryLabel.PERSONA in labels
        assert MemoryLabel.STATE in labels

    def test_letta_parse_has_labels(self, tmp_path: Path) -> None:
        """Letta parse produces labelled memory records."""
        state = {
            "memory": {
                "persona": {"value": "I am helpful"},
                "human": {"value": "User likes code"},
            },
            "system": "You are a helpful assistant.",
        }
        files = {
            "agent_state.json": json.dumps(state),
        }
        spawner = _get_spawner(SourceType.LETTA)
        result = spawner.parse(files)

        labels = {r.label for r in result.memory}
        assert MemoryLabel.FLOW in labels or MemoryLabel.PERSONA in labels
