"""Tests for pipeline helpers and phases."""

from __future__ import annotations

from pathlib import Path

import pytest

from pynydus.api.schemas import (
    Bucket,
    MemoryLabel,
    MemoryModule,
    MemoryRecord,
    RedactMode,
    SecretKind,
    SecretRecord,
    SecretsModule,
    SkillRecord,
    SkillsModule,
    SourceType,
)
from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective
from pynydus.engine.pipeline import (
    PipelineContext,
    _apply_bucket_filter,
    _phase8_package,
    _resolve_source_type,
)
from pynydus.engine.pipeline import _apply_custom_labels, _apply_secret_policy


# ---------------------------------------------------------------------------
# _apply_bucket_filter
# ---------------------------------------------------------------------------


class TestApplyBucketFilter:
    def _modules(self):
        skills = SkillsModule(
            skills=[SkillRecord(id="s1", name="x",
                                source_type="x", content="y")]
        )
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="y",
                    label=MemoryLabel.STATE,
                    source_framework="x",
                    source_store="x",
                )
            ]
        )
        secrets = SecretsModule(
            secrets=[
                SecretRecord(
                    id="s1",
                    placeholder="{{S}}",
                    kind=SecretKind.CREDENTIAL,
                    name="K",
                )
            ]
        )
        return skills, memory, secrets

    def test_all_buckets_included(self):
        s, m, sec = self._modules()
        rs, rm, rsec = _apply_bucket_filter(
            s, m, sec, {Bucket.SKILLS, Bucket.MEMORY, Bucket.SECRETS}
        )
        assert len(rs.skills) == 1
        assert len(rm.memory) == 1
        assert len(rsec.secrets) == 1

    def test_skills_excluded(self):
        s, m, sec = self._modules()
        rs, rm, rsec = _apply_bucket_filter(s, m, sec, {Bucket.MEMORY, Bucket.SECRETS})
        assert rs.skills == []
        assert len(rm.memory) == 1

    def test_memory_excluded(self):
        s, m, sec = self._modules()
        rs, rm, rsec = _apply_bucket_filter(s, m, sec, {Bucket.SKILLS, Bucket.SECRETS})
        assert rm.memory == []
        assert len(rs.skills) == 1

    def test_secrets_excluded(self):
        s, m, sec = self._modules()
        rs, rm, rsec = _apply_bucket_filter(s, m, sec, {Bucket.SKILLS, Bucket.MEMORY})
        assert rsec.secrets == []

    def test_empty_buckets(self):
        s, m, sec = self._modules()
        rs, rm, rsec = _apply_bucket_filter(s, m, sec, set())
        assert rs.skills == []
        assert rm.memory == []
        assert rsec.secrets == []


# ---------------------------------------------------------------------------
# _apply_custom_labels
# ---------------------------------------------------------------------------


class TestApplyCustomLabels:
    def test_pattern_match(self):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="x",
                    label=MemoryLabel.STATE,
                    source_framework="x",
                    source_store="soul.md",
                ),
                MemoryRecord(
                    id="m2",
                    text="y",
                    label=MemoryLabel.STATE,
                    source_framework="x",
                    source_store="knowledge.md",
                ),
            ]
        )
        _apply_custom_labels(
            memory,
            {
                "soul*": MemoryLabel.PERSONA.value,
                "knowledge*": MemoryLabel.STATE.value,
            },
        )
        assert memory.memory[0].label == MemoryLabel.PERSONA
        assert memory.memory[1].label == MemoryLabel.STATE

    def test_no_match(self):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="x",
                    label=MemoryLabel.FLOW,
                    source_framework="x",
                    source_store="other.md",
                ),
            ]
        )
        _apply_custom_labels(memory, {"soul*": MemoryLabel.PERSONA.value})
        assert memory.memory[0].label == MemoryLabel.FLOW

    def test_first_match_wins(self):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="x",
                    label=MemoryLabel.STATE,
                    source_framework="x",
                    source_store="soul.md",
                ),
            ]
        )
        _apply_custom_labels(
            memory,
            {
                "soul*": MemoryLabel.PERSONA.value,
                "*.md": MemoryLabel.STATE.value,
            },
        )
        assert memory.memory[0].label == MemoryLabel.PERSONA


# ---------------------------------------------------------------------------
# _apply_secret_policy
# ---------------------------------------------------------------------------


class TestApplySecretPolicy:
    def _make_egg(self):
        from datetime import UTC, datetime

        from pynydus.api.schemas import Egg, Manifest
        return Egg(
            manifest=Manifest(
                nydus_version="0.5.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["skills", "memory", "secrets"],
            ),
            secrets=SecretsModule(
                secrets=[
                    SecretRecord(id="s1", placeholder="{{S1}}", kind=SecretKind.CREDENTIAL,
                                 name="K1", required_at_hatch=False),
                    SecretRecord(id="s2", placeholder="{{S2}}", kind=SecretKind.PII,
                                 name="K2", required_at_hatch=True),
                ]
            ),
        )

    def test_all_required(self):
        egg = self._make_egg()
        _apply_secret_policy(egg, "all_required")
        assert all(s.required_at_hatch for s in egg.secrets.secrets)

    def test_none_required(self):
        egg = self._make_egg()
        _apply_secret_policy(egg, "none_required")
        assert not any(s.required_at_hatch for s in egg.secrets.secrets)


# ---------------------------------------------------------------------------
# _resolve_source_type
# ---------------------------------------------------------------------------


class TestResolveSourceType:
    def test_explicit_valid(self):
        result = _resolve_source_type(Path("/tmp"), "openclaw", None)
        assert result == SourceType.OPENCLAW

    def test_explicit_invalid(self):
        with pytest.raises(Exception, match="Unknown source type"):
            _resolve_source_type(Path("/tmp"), "bogus", None)

    def test_from_config(self):
        config = NydusfileConfig(source=SourceType.LETTA)
        result = _resolve_source_type(Path("/tmp"), None, config)
        assert result == SourceType.LETTA

    def test_auto_detect_openclaw(self, tmp_path: Path):
        (tmp_path / "soul.md").write_text("Hi")
        result = _resolve_source_type(tmp_path, None, None)
        assert result == SourceType.OPENCLAW

    def test_auto_detect_letta(self, tmp_path: Path):
        import json
        (tmp_path / "agent_state.json").write_text(json.dumps({"system": "test"}))
        result = _resolve_source_type(tmp_path, None, None)
        assert result == SourceType.LETTA

    def test_auto_detect_fails(self, tmp_path: Path):
        with pytest.raises(Exception, match="Cannot auto-detect"):
            _resolve_source_type(tmp_path, None, None)


# ---------------------------------------------------------------------------
# _phase8_package
# ---------------------------------------------------------------------------


class TestPhase8Package:
    def test_basic_packaging(self):
        ctx = PipelineContext(
            source_path=Path("/tmp/test"),
        )
        skills = SkillsModule(
            skills=[SkillRecord(id="s1", name="greet",
                                source_type="x", content="hi")]
        )
        memory = MemoryModule()
        secrets = SecretsModule()

        egg = _phase8_package(
            ctx, SourceType.OPENCLAW, skills, memory, secrets,
            {"k": "v"},
            {Bucket.SKILLS, Bucket.MEMORY, Bucket.SECRETS},
        )
        assert egg.manifest.source_type == SourceType.OPENCLAW
        assert len(egg.skills.skills) == 1
        assert egg.manifest.source_metadata == {"k": "v"}

    def test_sources_in_manifest(self):
        config = NydusfileConfig(
            source=SourceType.OPENCLAW,
            sources=[
                SourceDirective(source_type="openclaw", path="/a"),
                SourceDirective(source_type="letta", path="/b"),
            ],
        )
        ctx = PipelineContext(
            source_path=Path("/tmp/test"),
            nydusfile_config=config,
        )
        egg = _phase8_package(
            ctx, SourceType.OPENCLAW, SkillsModule(), MemoryModule(),
            SecretsModule(), {},
            {Bucket.SKILLS, Bucket.MEMORY, Bucket.SECRETS},
        )
        assert len(egg.manifest.sources) == 2
        assert egg.manifest.sources[0].source_type == "openclaw"
        assert egg.manifest.sources[1].source_path == "/b"



# ---------------------------------------------------------------------------
# PipelineContext
# ---------------------------------------------------------------------------


class TestPipelineContext:
    def test_defaults(self):
        ctx = PipelineContext(source_path=Path("/tmp"))
        assert ctx.source_type is None
        assert ctx.redact_mode == RedactMode.PII
        assert ctx.spawn_log == []

    def test_custom_values(self):
        ctx = PipelineContext(
            source_path=Path("/tmp"),
            source_type=SourceType.LETTA,
            redact_mode=RedactMode.ALL,
        )
        assert ctx.source_type == SourceType.LETTA
        assert ctx.redact_mode == RedactMode.ALL


