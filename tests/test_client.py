"""Tests for the Python SDK (client/client.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pynydus import Nydus
from pynydus.api.schemas import (
    DiffReport,
    Egg,
    HatchResult,
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
    ValidationReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def openclaw_source(tmp_path: Path) -> Path:
    src = tmp_path / "source"
    src.mkdir()
    (src / "soul.md").write_text("I am a helpful assistant.\n\nI prefer short answers.\n")
    (src / "knowledge.md").write_text("The sky is blue.\n")
    (src / "skill.md").write_text("# Search\nDo a web search.\n")
    return src


@pytest.fixture
def nydusfile(openclaw_source: Path, tmp_path: Path) -> Path:
    """Create a Nydusfile pointing to the openclaw_source fixture."""
    nf = tmp_path / "Nydusfile"
    nf.write_text(f"SOURCE openclaw {openclaw_source}\n")
    return nf


@pytest.fixture
def nydus() -> Nydus:
    """SDK client with no config (LLM disabled)."""
    return Nydus()


# ---------------------------------------------------------------------------
# Spawn
# ---------------------------------------------------------------------------


class TestSpawn:
    def test_spawn_returns_egg(self, nydus: Nydus, nydusfile: Path):
        egg = nydus.spawn(nydusfile=nydusfile)

        assert isinstance(egg, Egg)
        assert len(egg.skills.skills) >= 1
        assert len(egg.memory.memory) >= 1
        assert egg.spawn_attachments is not None
        assert isinstance(egg.spawn_attachments.raw_artifacts, dict)
        assert len(egg.spawn_attachments.raw_artifacts) > 0

    def test_spawn_with_redact_none(self, nydus: Nydus, openclaw_source: Path, tmp_path: Path):
        nf = tmp_path / "Nydusfile"
        nf.write_text(f"SOURCE openclaw {openclaw_source}\nREDACT none\n")
        egg = nydus.spawn(nydusfile=nf)
        assert len(egg.memory.memory) >= 1

    def test_spawn_reads_nydusfile(self, nydus: Nydus, nydusfile: Path):
        egg = nydus.spawn(nydusfile=nydusfile)
        assert egg.manifest.source_type == SourceType.OPENCLAW

    def test_spawn_attaches_logs(self, nydus: Nydus, nydusfile: Path):
        egg = nydus.spawn(nydusfile=nydusfile)
        assert egg.spawn_attachments is not None
        assert isinstance(egg.spawn_attachments.logs, dict)

    def test_spawn_no_nydusfile_raises(self, nydus: Nydus, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="Nydusfile not found"):
            nydus.spawn(nydusfile=tmp_path / "nonexistent" / "Nydusfile")

    def test_relative_source_when_cwd_not_nydusfile_dir(
        self,
        nydus: Nydus,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Relative SOURCE paths resolve against the Nydusfile directory, not cwd."""
        project = tmp_path / "proj"
        project.mkdir()
        agent = project / "agent"
        agent.mkdir()
        (agent / "soul.md").write_text("I am helpful.\n")
        (agent / "knowledge.md").write_text("Fact.\n")
        (agent / "skill.md").write_text("# Search\nSearch the web.\n")

        nydusfile = project / "Nydusfile"
        nydusfile.write_text("SOURCE openclaw ./agent\n")

        other = tmp_path / "other"
        other.mkdir()
        monkeypatch.chdir(other)

        egg = nydus.spawn(nydusfile=nydusfile.resolve())

        assert len(egg.skills.skills) >= 1
        assert len(egg.memory.memory) >= 1


# ---------------------------------------------------------------------------
# Modules accessor
# ---------------------------------------------------------------------------


class TestModulesAccessor:
    def test_modules_skills(self, nydus: Nydus, nydusfile: Path):
        egg = nydus.spawn(nydusfile=nydusfile)
        assert egg.modules.skills is egg.skills.skills
        assert len(egg.modules.skills) >= 1

    def test_modules_memory(self, nydus: Nydus, nydusfile: Path):
        egg = nydus.spawn(nydusfile=nydusfile)
        assert egg.modules.memory is egg.memory.memory
        assert len(egg.modules.memory) >= 1

    def test_modules_secrets(self, nydus: Nydus, nydusfile: Path):
        egg = nydus.spawn(nydusfile=nydusfile)
        assert egg.modules.secrets is egg.secrets.secrets


class TestInspectSecrets:
    def test_inspect_secrets_format(self):
        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["secrets"],
            ),
            secrets=SecretsModule(
                secrets=[
                    SecretRecord(
                        id="s1",
                        placeholder="{{API_KEY}}",
                        kind=SecretKind.CREDENTIAL,
                        name="API_KEY",
                        required_at_hatch=True,
                        injection_mode=InjectionMode.ENV,
                        occurrences=["skills/search/SKILL.md"],
                    )
                ]
            ),
        )
        result = egg.inspect_secrets()
        assert len(result) == 1
        assert result[0]["placeholder"] == "{{API_KEY}}"
        assert result[0]["name"] == "API_KEY"
        assert result[0]["kind"] == "credential"
        assert result[0]["required"] is True
        assert result[0]["occurrences"] == ["skills/search/SKILL.md"]

    def test_inspect_secrets_empty(self):
        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=[],
            ),
        )
        assert egg.inspect_secrets() == []


# ---------------------------------------------------------------------------
# Pack / Unpack
# ---------------------------------------------------------------------------


class TestPackUnpack:
    def test_roundtrip(self, nydus: Nydus, nydusfile: Path, tmp_path: Path):
        egg = nydus.spawn(nydusfile=nydusfile)
        egg_path = nydus.pack(egg, output=tmp_path / "test.egg")

        assert egg_path.exists()
        assert egg_path.suffix == ".egg"

        loaded = nydus.unpack(egg_path)
        assert len(loaded.skills.skills) == len(egg.skills.skills)
        assert len(loaded.memory.memory) == len(egg.memory.memory)
        assert loaded.manifest.source_type == egg.manifest.source_type

    def test_pack_with_explicit_raw(self, nydus: Nydus, nydusfile: Path, tmp_path: Path):
        egg = nydus.spawn(nydusfile=nydusfile)
        assert egg.spawn_attachments is not None
        egg_path = nydus.pack(
            egg, output=tmp_path / "test.egg",
            raw_artifacts=egg.spawn_attachments.raw_artifacts,
            logs=egg.spawn_attachments.logs,
        )
        assert egg_path.exists()


# ---------------------------------------------------------------------------
# Hatch
# ---------------------------------------------------------------------------


class TestHatch:
    def test_hatch_produces_files(self, nydus: Nydus, nydusfile: Path, tmp_path: Path):
        egg = nydus.spawn(nydusfile=nydusfile)
        out = tmp_path / "hatched"

        result = nydus.hatch(egg, target="openclaw", output_dir=out)

        assert isinstance(result, HatchResult)
        assert len(result.files_created) > 0
        assert result.output_dir == out

    def test_hatch_to_different_target(self, nydus: Nydus, nydusfile: Path, tmp_path: Path):
        egg = nydus.spawn(nydusfile=nydusfile)
        out = tmp_path / "hatched_letta"

        result = nydus.hatch(egg, target="letta", output_dir=out)

        assert result.target == "letta"
        assert "agent_state.json" in result.files_created

    def test_hatch_accepts_string_secrets(self, nydus: Nydus, nydusfile: Path, tmp_path: Path):
        egg = nydus.spawn(nydusfile=nydusfile)
        env_file = tmp_path / "agent.env"
        env_file.write_text("API_KEY=sk-test\n")
        out = tmp_path / "hatched"

        result = nydus.hatch(egg, target="openclaw", output_dir=out, secrets=str(env_file))
        assert result.output_dir == out


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_valid_egg(self, nydus: Nydus, nydusfile: Path):
        egg = nydus.spawn(nydusfile=nydusfile)
        report = nydus.validate(egg)

        assert isinstance(report, ValidationReport)
        assert report.valid

    def test_invalid_egg_duplicate_ids(self, nydus: Nydus):
        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime(2024, 1, 1, tzinfo=UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["skills"],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="dup",
                        name="A",
                        source_type="markdown_skill",
                        content="a",
                    ),
                    SkillRecord(
                        id="dup",
                        name="B",
                        source_type="markdown_skill",
                        content="b",
                    ),
                ]
            ),
        )
        report = nydus.validate(egg)
        assert not report.valid


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


class TestDiff:
    def test_identical(self, nydus: Nydus, nydusfile: Path):
        egg = nydus.spawn(nydusfile=nydusfile)
        report = nydus.diff(egg, egg)

        assert isinstance(report, DiffReport)
        assert report.identical

    def test_different(self, nydus: Nydus):
        egg_a = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime(2024, 1, 1, tzinfo=UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["skills"],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="s1",
                        name="Old",
                        source_type="markdown_skill",
                        content="old",
                    )
                ]
            ),
        )
        egg_b = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime(2024, 1, 1, tzinfo=UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["skills"],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="s1",
                        name="New",
                        source_type="markdown_skill",
                        content="new",
                    )
                ]
            ),
        )
        report = nydus.diff(egg_a, egg_b)
        assert not report.identical
        assert len(report.entries) > 0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_no_config(self, tmp_path: Path):
        """Nydus() works without a config file — LLM disabled."""
        from unittest.mock import patch

        with patch.object(Path, "cwd", return_value=tmp_path):
            nydus = Nydus()
            assert nydus._config.llm is None

    def test_config_loaded(self, tmp_path: Path):
        import json

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "llm": {
                        "simple": {
                            "provider": "anthropic",
                            "model": "claude-haiku-4-5-20251001",
                            "api_key": "sk-test",
                        },
                        "complex": {
                            "provider": "anthropic",
                            "model": "claude-sonnet-4-20250514",
                            "api_key": "sk-test",
                        },
                    }
                }
            )
        )
        nydus = Nydus(config_path=config_file)
        assert nydus._config.llm is not None
        assert nydus._config.llm.simple.provider == "anthropic"


# ---------------------------------------------------------------------------
# Push / Pull stubs
# ---------------------------------------------------------------------------


class TestRegistryStubs:
    def test_push_without_registry_raises_config_error(self, nydus: Nydus, tmp_path: Path):
        from pynydus.api.errors import ConfigError

        egg_file = tmp_path / "test.egg"
        egg_file.write_bytes(b"data")
        with pytest.raises(ConfigError, match="Registry not configured"):
            nydus.push(egg_file, name="test/egg", version="0.1.0")

    def test_pull_without_registry_raises_config_error(self, nydus: Nydus):
        from pynydus.api.errors import ConfigError

        with pytest.raises(ConfigError, match="Registry not configured"):
            nydus.pull("test/egg", version="0.1.0")

    def test_pull_defaults_to_latest(self, nydus: Nydus):
        from pynydus.api.errors import ConfigError

        with pytest.raises(ConfigError, match="Registry not configured"):
            nydus.pull("test/egg")
