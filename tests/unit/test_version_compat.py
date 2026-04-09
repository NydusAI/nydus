"""Tests for version compatibility checking at hatch time."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pynydus.api.errors import HatchError
from pynydus.api.schemas import (
    Egg,
    Manifest,
    MemoryModule,
    SecretsModule,
    SkillsModule,
)
from pynydus.common.enums import AgentType, Bucket
from pynydus.engine.hatcher import _check_version_compat, _parse_version

# ---------------------------------------------------------------------------
# _parse_version
# ---------------------------------------------------------------------------


class TestParseVersion:
    def test_simple(self):
        assert _parse_version("0.1.0") == (0, 1, 0)

    def test_major_minor_patch(self):
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_two_digit(self):
        assert _parse_version("10.20.30") == (10, 20, 30)

    def test_comparison(self):
        assert _parse_version("0.1.0") < _parse_version("0.2.0")
        assert _parse_version("0.2.0") < _parse_version("1.0.0")
        assert _parse_version("1.0.0") == _parse_version("1.0.0")
        assert _parse_version("0.1.0") < _parse_version("0.1.1")


# ---------------------------------------------------------------------------
# _check_version_compat
# ---------------------------------------------------------------------------


def _make_egg(min_nydus_version: str = "0.1.0") -> Egg:
    return Egg(
        manifest=Manifest(
            nydus_version="0.1.0",
            min_nydus_version=min_nydus_version,
            created_at=datetime.now(UTC),
            agent_type=AgentType.OPENCLAW,
            included_modules=[Bucket.SKILL, Bucket.MEMORY],
        ),
    )


class TestVersionCompat:
    def test_same_version_passes(self):
        """Current version == min_nydus_version should pass."""
        egg = _make_egg("0.1.0")
        # Should not raise
        _check_version_compat(egg)

    def test_newer_current_passes(self):
        """Current version > min_nydus_version should pass."""
        egg = _make_egg("0.0.1")
        _check_version_compat(egg)

    def test_older_current_fails(self):
        """Current version < min_nydus_version should raise HatchError."""
        egg = _make_egg("99.0.0")
        with pytest.raises(HatchError, match="requires nydus >= 99.0.0"):
            _check_version_compat(egg)

    def test_error_message_includes_upgrade_hint(self):
        egg = _make_egg("99.0.0")
        with pytest.raises(HatchError, match="Please upgrade"):
            _check_version_compat(egg)

    def test_missing_min_version_passes(self):
        """Eggs without min_nydus_version should pass (backward compat)."""
        egg = _make_egg("0.1.0")
        # Simulate old egg without the field
        egg.manifest.min_nydus_version = ""  # type: ignore[assignment]
        # Should not raise (falsy value skips check)
        _check_version_compat(egg)

    def test_malformed_version_skips(self):
        """Malformed version strings should skip the check, not crash."""
        egg = _make_egg("not.a.version")
        # Should not raise — gracefully skip
        _check_version_compat(egg)

    def test_hatch_egg_with_future_version(self, tmp_path: Path):
        """Hatching an egg that requires a future version should fail."""
        from pynydus.engine.hatcher import hatch

        egg = Egg(
            manifest=Manifest(
                nydus_version="99.0.0",
                min_nydus_version="99.0.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
                source_metadata={},
            ),
            skills=SkillsModule(skills=[]),
            memory=MemoryModule(memory=[]),
            secrets=SecretsModule(secrets=[]),
        )
        with pytest.raises(HatchError, match="requires nydus >= 99.0.0"):
            hatch(egg, target="openclaw", output_dir=tmp_path / "out")
