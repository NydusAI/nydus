"""Tests for Nydusfile enhancements (Priority 3.3).

Covers: EXCLUDE_FILES, LABEL, SECRET_POLICY directives.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pynydus.api.errors import NydusfileError
from pynydus.api.schemas import (
    Egg,
    InjectionMode,
    Manifest,
    MemoryLabel,
    MemoryModule,
    MemoryRecord,
    SecretKind,
    SecretRecord,
    SecretsModule,
    SkillRecord,
    SkillsModule,
    SourceType,
)
from pynydus.engine.nydusfile import NydusfileConfig, parse
from pynydus.engine.pipeline import _apply_custom_labels, _apply_secret_policy


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------


class TestExcludeFilesParsing:
    def test_single_pattern(self):
        cfg = parse("SOURCE openclaw ./src\nEXCLUDE_FILES *.log")
        assert cfg.exclude_files == ["*.log"]

    def test_multiple_patterns(self):
        cfg = parse("SOURCE openclaw ./src\nEXCLUDE_FILES *.log\nEXCLUDE_FILES temp_*")
        assert cfg.exclude_files == ["*.log", "temp_*"]

    def test_no_arg_raises(self):
        with pytest.raises(NydusfileError, match="requires a glob"):
            parse("SOURCE openclaw ./src\nEXCLUDE_FILES")

    def test_default_empty(self):
        cfg = parse("SOURCE openclaw ./src")
        assert cfg.exclude_files == []


class TestLabelParsing:
    def test_single_label(self):
        cfg = parse("SOURCE openclaw ./src\nLABEL soul.md flow")
        assert cfg.custom_labels == {"soul.md": "flow"}

    def test_multiple_labels(self):
        cfg = parse(
            "SOURCE openclaw ./src\nLABEL soul.md flow\nLABEL knowledge.md state"
        )
        assert cfg.custom_labels == {"soul.md": "flow", "knowledge.md": "state"}

    def test_no_arg_raises(self):
        with pytest.raises(NydusfileError, match="requires"):
            parse("SOURCE openclaw ./src\nLABEL")

    def test_single_arg_raises(self):
        with pytest.raises(NydusfileError, match="two arguments"):
            parse("SOURCE openclaw ./src\nLABEL soul.md")

    def test_default_empty(self):
        cfg = parse("SOURCE openclaw ./src")
        assert cfg.custom_labels == {}


class TestSecretPolicyParsing:
    def test_all_required(self):
        cfg = parse("SOURCE openclaw ./src\nSECRET_POLICY all_required")
        assert cfg.secret_policy == "all_required"

    def test_none_required(self):
        cfg = parse("SOURCE openclaw ./src\nSECRET_POLICY none_required")
        assert cfg.secret_policy == "none_required"

    def test_default_value(self):
        cfg = parse("SOURCE openclaw ./src")
        assert cfg.secret_policy == "default"

    def test_invalid_raises(self):
        with pytest.raises(NydusfileError, match="Unknown secret policy"):
            parse("SOURCE openclaw ./src\nSECRET_POLICY invalid")

    def test_duplicate_raises(self):
        with pytest.raises(NydusfileError, match="Duplicate"):
            parse("SOURCE openclaw ./src\nSECRET_POLICY all_required\nSECRET_POLICY none_required")

    def test_no_arg_raises(self):
        with pytest.raises(NydusfileError, match="requires a policy"):
            parse("SOURCE openclaw ./src\nSECRET_POLICY")


class TestFullNydusfile:
    def test_all_new_directives(self):
        text = """\
SOURCE openclaw ./src
REDACT pii
EXCLUDE_FILES *.log
EXCLUDE_FILES temp_*
LABEL soul.md flow
LABEL knowledge.md state
SECRET_POLICY all_required
PURPOSE "test agent"
"""
        cfg = parse(text)
        assert cfg.source == SourceType.OPENCLAW
        assert cfg.exclude_files == ["*.log", "temp_*"]
        assert cfg.custom_labels == {"soul.md": "flow", "knowledge.md": "state"}
        assert cfg.secret_policy == "all_required"
        assert cfg.purpose == "test agent"


# ---------------------------------------------------------------------------
# Spawner integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_partial():
    """Create an EggPartial-like object for testing helpers."""
    from pynydus.api.schemas import EggPartial

    return EggPartial(
        skills=SkillsModule(
            skills=[
                SkillRecord(
                    id="skill_001",
                    name="search",
                    source_type="skill.md",
                    content="search the web",
                ),
                SkillRecord(
                    id="skill_002",
                    name="temp skill",
                    source_type="temp_skill.md",
                    content="temporary",
                ),
            ]
        ),
        memory=MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="I am a helpful assistant.",
                    label=MemoryLabel.PERSONA,
                    source_framework="openclaw",
                    source_store="soul.md",
                ),
                MemoryRecord(
                    id="mem_002",
                    text="Python is great.",
                    label=MemoryLabel.STATE,
                    source_framework="openclaw",
                    source_store="knowledge.md",
                ),
                MemoryRecord(
                    id="mem_003",
                    text="Debug log content",
                    label=MemoryLabel.CONTEXT,
                    source_framework="openclaw",
                    source_store="debug.log",
                ),
            ]
        ),
        secrets=SecretsModule(secrets=[]),
        raw_artifacts={
            "soul.md": "# Soul\nI am a helper.",
            "knowledge.md": "# Knowledge\nPython.",
            "debug.log": "DEBUG: some log",
        },
    )


class TestApplyCustomLabels:
    def test_labels_applied(self, sample_partial):
        _apply_custom_labels(
            sample_partial.memory, {"soul.md": "flow", "knowledge.md": "state"}
        )
        labels = {r.source_store: r.label for r in sample_partial.memory.memory}
        assert labels["soul.md"] == MemoryLabel.FLOW
        assert labels["knowledge.md"] == MemoryLabel.STATE

    def test_no_match_unchanged(self, sample_partial):
        _apply_custom_labels(sample_partial.memory, {"nonexistent": "flow"})
        labels = [r.label for r in sample_partial.memory.memory]
        assert labels == [MemoryLabel.PERSONA, MemoryLabel.STATE, MemoryLabel.CONTEXT]

    def test_glob_pattern(self, sample_partial):
        _apply_custom_labels(sample_partial.memory, {"*.md": "context"})
        md_records = [
            r for r in sample_partial.memory.memory if r.source_store.endswith(".md")
        ]
        assert all(r.label == MemoryLabel.CONTEXT for r in md_records)


class TestApplySecretPolicy:
    def test_all_required(self):
        egg = _make_egg_with_secrets([
            _secret("s1", required=False),
            _secret("s2", required=True),
        ])
        _apply_secret_policy(egg, "all_required")
        assert all(s.required_at_hatch for s in egg.secrets.secrets)

    def test_none_required(self):
        egg = _make_egg_with_secrets([
            _secret("s1", required=True),
            _secret("s2", required=True),
        ])
        _apply_secret_policy(egg, "none_required")
        assert not any(s.required_at_hatch for s in egg.secrets.secrets)


# ---------------------------------------------------------------------------
# End-to-end: spawn with Nydusfile containing new directives
# ---------------------------------------------------------------------------


class TestSpawnWithEnhancements:
    def test_exclude_files_in_spawn(self, tmp_path: Path):
        """EXCLUDE_FILES filters files during spawn."""
        from pynydus.engine.pipeline import build as spawn

        (tmp_path / "soul.md").write_text("# Soul\nI am helpful.")
        (tmp_path / "knowledge.md").write_text("# Knowledge\nFacts.")
        (tmp_path / "debug.log").write_text("debug stuff")

        nydusfile = NydusfileConfig(
            source=SourceType.OPENCLAW,
            exclude_files=["*.log"],
        )
        egg, raw, logs = spawn(
            tmp_path, source_type="openclaw", nydusfile_config=nydusfile
        )
        # debug.log should be excluded from raw artifacts
        assert "debug.log" not in raw

    def test_custom_labels_in_spawn(self, tmp_path: Path):
        """LABEL directives set labels before enrichment."""
        from pynydus.engine.pipeline import build as spawn

        (tmp_path / "soul.md").write_text("# Soul\nI am an AI assistant.")
        (tmp_path / "knowledge.md").write_text("# Knowledge\nFacts about Python.")

        nydusfile = NydusfileConfig(
            source=SourceType.OPENCLAW,
            custom_labels={"soul.md": "flow", "knowledge.md": "context"},
        )
        egg, raw, logs = spawn(
            tmp_path, source_type="openclaw", nydusfile_config=nydusfile
        )
        labels = {r.source_store: r.label for r in egg.memory.memory if r.source_store}
        assert labels.get("soul.md") == MemoryLabel.FLOW
        assert labels.get("knowledge.md") == MemoryLabel.CONTEXT

    def test_secret_policy_in_spawn(self, tmp_path: Path):
        """SECRET_POLICY overrides required_at_hatch."""
        from pynydus.engine.pipeline import build as spawn

        (tmp_path / "soul.md").write_text(
            "# Soul\nMy API key is sk-1234567890abcdef."
        )

        nydusfile = NydusfileConfig(
            source=SourceType.OPENCLAW,
            secret_policy="none_required",
        )
        egg, raw, logs = spawn(
            tmp_path, source_type="openclaw", nydusfile_config=nydusfile
        )
        # Any PII-detected secrets should have required_at_hatch=False
        for secret in egg.secrets.secrets:
            assert secret.required_at_hatch is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _secret(name: str, *, required: bool) -> SecretRecord:
    return SecretRecord(
        id=f"secret_{name}",
        placeholder=f"{{{{SECRET_{name}}}}}",
        kind=SecretKind.CREDENTIAL,
        name=name,
        required_at_hatch=required,
        injection_mode=InjectionMode.ENV,
    )


def _make_egg_with_secrets(secrets: list[SecretRecord]) -> Egg:
    return Egg(
        manifest=Manifest(
            nydus_version="0.1.0",
            created_at=datetime.now(UTC),
            source_type=SourceType.OPENCLAW,
            included_modules=["secrets"],
            source_metadata={},
        ),
        skills=SkillsModule(skills=[]),
        memory=MemoryModule(memory=[]),
        secrets=SecretsModule(secrets=secrets),
    )
