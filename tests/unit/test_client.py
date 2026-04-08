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
    Manifest,
    SecretRecord,
    SecretsModule,
    SkillRecord,
    SkillsModule,
    ValidationReport,
)
from pynydus.common.enums import (
    AgentType,
    Bucket,
    InjectionMode,
    SecretKind,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def openclaw_source(tmp_path: Path) -> Path:
    src = tmp_path / "source"
    src.mkdir()
    (src / "SOUL.md").write_text("I am a helpful assistant.\n\nI prefer short answers.\n")
    (src / "MEMORY.md").write_text("The sky is blue.\n")
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
        assert egg.manifest.agent_type == AgentType.OPENCLAW
        assert isinstance(egg.spawn_log, list)
        assert len(egg.skills.skills) >= 1
        assert len(egg.memory.memory) >= 1
        assert isinstance(egg.raw_artifacts, dict)
        assert len(egg.raw_artifacts) > 0

    def test_spawn_no_nydusfile_raises(self, nydus: Nydus, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
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
        (agent / "SOUL.md").write_text("I am helpful.\n")
        (agent / "MEMORY.md").write_text("Fact.\n")
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


class TestInspectSecrets:
    def test_inspect_secrets_format(self):
        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SECRET],
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
                agent_type=AgentType.OPENCLAW,
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
        egg_path = nydus.save(
            egg,
            tmp_path / "test.egg",
            raw_artifacts=egg.raw_artifacts,
            spawn_log=egg.spawn_log,
        )

        assert egg_path.exists()
        assert egg_path.suffix == ".egg"

        loaded = nydus.load(egg_path)
        assert len(loaded.skills.skills) == len(egg.skills.skills)
        assert len(loaded.memory.memory) == len(egg.memory.memory)
        assert loaded.manifest.agent_type == egg.manifest.agent_type


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
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="dup",
                        name="A",
                        agent_type="markdown_skill",
                        content="a",
                    ),
                    SkillRecord(
                        id="dup",
                        name="B",
                        agent_type="markdown_skill",
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
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="s1",
                        name="Old",
                        agent_type="markdown_skill",
                        content="old",
                    )
                ]
            ),
        )
        egg_b = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime(2024, 1, 1, tzinfo=UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="s1",
                        name="New",
                        agent_type="markdown_skill",
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
    def test_default_no_llm_env(self, monkeypatch: pytest.MonkeyPatch):
        """Nydus() has no LLM tier when env vars are unset."""
        monkeypatch.delenv("NYDUS_LLM_TYPE", raising=False)
        monkeypatch.delenv("NYDUS_LLM_API_KEY", raising=False)
        nydus = Nydus()
        assert nydus._config.llm is None

    def test_llm_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NYDUS_LLM_TYPE", "anthropic/claude-haiku-4-5-20251001")
        monkeypatch.setenv("NYDUS_LLM_API_KEY", "sk-test")
        nydus = Nydus()
        assert nydus._config.llm is not None
        assert nydus._config.llm.provider == "anthropic"


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
