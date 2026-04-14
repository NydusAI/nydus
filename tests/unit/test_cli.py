"""CLI integration tests (Priority 4.1).

Uses typer.testing.CliRunner to exercise each CLI command end-to-end.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pynydus.cmd.main import app
from typer.testing import CliRunner

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def openclaw_source(tmp_path: Path) -> Path:
    """Create a minimal OpenClaw source directory."""
    (tmp_path / "SOUL.md").write_text("# Soul\nI am a helpful AI assistant.")
    (tmp_path / "MEMORY.md").write_text("# Knowledge\nPython is a language.")
    return tmp_path


@pytest.fixture
def spawned_egg(openclaw_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Spawn an egg via Nydusfile and return the .egg path."""
    nydusfile = tmp_path / "Nydusfile"
    nydusfile.write_text(f"SOURCE openclaw {openclaw_source}\n")
    monkeypatch.chdir(tmp_path)
    egg_path = tmp_path / "test.egg"
    result = runner.invoke(app, ["spawn", "-o", str(egg_path)])
    assert result.exit_code == 0, result.output
    assert egg_path.exists()
    return egg_path


# ---------------------------------------------------------------------------
# spawn
# ---------------------------------------------------------------------------


class TestSpawnCommand:
    def test_spawn_openclaw_basic(
        self, openclaw_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_source}\n")
        monkeypatch.chdir(tmp_path)
        egg_path = tmp_path / "out.egg"
        result = runner.invoke(app, ["spawn", "-o", str(egg_path)])
        assert result.exit_code == 0
        assert "Egg spawned" in result.output
        assert egg_path.exists()
        assert "skills=" in result.output
        assert "memory=" in result.output
        assert "secrets=" in result.output
        assert "unsigned" in result.output

    def test_spawn_no_nydusfile(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["spawn", "-o", str(tmp_path / "out.egg")])
        assert result.exit_code == 1
        assert "No Nydusfile found" in result.output

    def test_spawn_auto_signs_when_key_available(
        self, openclaw_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from pynydus.security.signing import generate_keypair

        key_dir = tmp_path / "keys"
        generate_keypair(key_dir)
        pem_data = (key_dir / "private.pem").read_text()
        monkeypatch.setenv("NYDUS_PRIVATE_KEY", pem_data)

        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_source}\n")
        monkeypatch.chdir(tmp_path)
        egg_path = tmp_path / "signed.egg"
        result = runner.invoke(app, ["spawn", "-o", str(egg_path)])
        assert result.exit_code == 0
        assert "signed" in result.output.lower()


# ---------------------------------------------------------------------------
# hatch
# ---------------------------------------------------------------------------


class TestHatchCommand:
    def test_hatch_to_openclaw(self, spawned_egg: Path, tmp_path: Path):
        out_dir = tmp_path / "hatched"
        result = runner.invoke(
            app,
            [
                "hatch",
                str(spawned_egg),
                "--target",
                "openclaw",
                "-o",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Hatched into openclaw" in result.output
        assert out_dir.exists()

    def test_hatch_missing_egg(self, tmp_path: Path):
        result = runner.invoke(
            app,
            [
                "hatch",
                str(tmp_path / "nope.egg"),
                "--target",
                "openclaw",
            ],
        )
        assert result.exit_code == 1

    def test_hatch_passthrough_flag(self, spawned_egg: Path, tmp_path: Path):
        out_dir = tmp_path / "hatched_pt"
        result = runner.invoke(
            app,
            [
                "hatch",
                str(spawned_egg),
                "--target",
                "openclaw",
                "--passthrough",
                "-o",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0
        assert out_dir.exists()

    def test_hatch_skip_validation_flag(self, spawned_egg: Path, tmp_path: Path):
        out_dir = tmp_path / "hatched_skip"
        result = runner.invoke(
            app,
            [
                "hatch",
                str(spawned_egg),
                "--target",
                "openclaw",
                "--skip-validation",
                "-o",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Hatched into openclaw" in result.output


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


class TestInspectCommand:
    def test_inspect_basic(self, spawned_egg: Path):
        result = runner.invoke(app, ["inspect", str(spawned_egg), "--secrets", "--logs"])
        assert result.exit_code == 0
        assert "Egg:" in result.output
        assert "nydus" in result.output
        assert "openclaw" in result.output.lower()

    def test_inspect_includes_validation(self, spawned_egg: Path):
        result = runner.invoke(app, ["inspect", str(spawned_egg)])
        assert result.exit_code == 0
        assert "validation:" in result.output

    def test_inspect_no_validate_flag(self, spawned_egg: Path):
        result = runner.invoke(app, ["inspect", str(spawned_egg), "--no-validate"])
        assert result.exit_code == 0
        assert "validation:" not in result.output

    def test_inspect_missing_egg(self, tmp_path: Path):
        result = runner.invoke(app, ["inspect", str(tmp_path / "nope.egg")])
        assert result.exit_code == 1
        assert "Error" in result.output


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


class TestExtractCommand:
    def test_extract_mcp_empty(self, spawned_egg: Path, tmp_path: Path):
        out = tmp_path / "ext_mcp"
        result = runner.invoke(app, ["extract", "mcp", "--from", str(spawned_egg), "-o", str(out)])
        assert result.exit_code == 0
        assert "No MCP config" in result.output

    def test_extract_skills_from_egg_with_skills(
        self, openclaw_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skills_dir = openclaw_source / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        (skills_dir / "greet.md").write_text("Say hello to the user warmly.\n")
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_source}\n")
        monkeypatch.chdir(tmp_path)
        egg_path = tmp_path / "skilled.egg"
        result = runner.invoke(app, ["spawn", "-o", str(egg_path)])
        assert result.exit_code == 0, result.output

        out = tmp_path / "ext_skills"
        result = runner.invoke(app, ["extract", "skills", "--from", str(egg_path), "-o", str(out)])
        assert result.exit_code == 0
        assert "Extracted" in result.output
        assert any(out.rglob("SKILL.md"))

    def test_extract_a2a(self, spawned_egg: Path, tmp_path: Path):
        out = tmp_path / "ext_a2a"
        result = runner.invoke(app, ["extract", "a2a", "--from", str(spawned_egg), "-o", str(out)])
        assert result.exit_code == 0
        assert "Extracted" in result.output
        assert (out / "agent-card.json").exists()

    def test_extract_apm_absent(self, spawned_egg: Path, tmp_path: Path):
        out = tmp_path / "ext_apm"
        result = runner.invoke(app, ["extract", "apm", "--from", str(spawned_egg), "-o", str(out)])
        assert result.exit_code == 0
        assert "No apm.yml" in result.output

    def test_extract_agents(self, spawned_egg: Path, tmp_path: Path):
        out = tmp_path / "ext_agents"
        result = runner.invoke(
            app, ["extract", "agents", "--from", str(spawned_egg), "-o", str(out)]
        )
        assert result.exit_code == 0
        assert "Extracted" in result.output
        assert (out / "AGENTS.md").exists()

    def test_extract_specs(self, spawned_egg: Path, tmp_path: Path):
        out = tmp_path / "ext_specs"
        result = runner.invoke(
            app, ["extract", "specs", "--from", str(spawned_egg), "-o", str(out)]
        )
        assert result.exit_code == 0
        assert "Extracted" in result.output
        assert (out / "manifest.json").exists()

    def test_extract_all(self, spawned_egg: Path, tmp_path: Path):
        out = tmp_path / "ext_all"
        result = runner.invoke(app, ["extract", "all", "--from", str(spawned_egg), "-o", str(out)])
        assert result.exit_code == 0
        assert "Extracted" in result.output
        assert out.exists()

    def test_extract_missing_egg(self, tmp_path: Path):
        result = runner.invoke(
            app, ["extract", "mcp", "--from", str(tmp_path / "nope.egg"), "-o", str(tmp_path)]
        )
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_extract_help(self):
        result = runner.invoke(app, ["extract", "--help"])
        assert result.exit_code == 0
        assert "extract" in result.output.lower()


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


class TestDiffCommand:
    def test_diff_different(
        self, openclaw_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_source}\n")
        monkeypatch.chdir(tmp_path)

        egg1 = tmp_path / "a.egg"
        egg2 = tmp_path / "b.egg"

        result = runner.invoke(app, ["spawn", "-o", str(egg1)])
        assert result.exit_code == 0

        (openclaw_source / "extra.md").write_text("# Extra\nSomething different.")
        result = runner.invoke(app, ["spawn", "-o", str(egg2)])
        assert result.exit_code == 0

        result = runner.invoke(app, ["diff", str(egg1), str(egg2)])
        assert result.exit_code == 0
        assert "change" in result.output.lower() or "diff" in result.output.lower()

    def test_diff_missing_egg(self, spawned_egg: Path, tmp_path: Path):
        result = runner.invoke(app, ["diff", str(spawned_egg), str(tmp_path / "nope.egg")])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDeleteCommand:
    def test_delete_existing(self, spawned_egg: Path):
        assert spawned_egg.exists()
        result = runner.invoke(app, ["delete", str(spawned_egg)])
        assert result.exit_code == 0
        assert "Deleted" in result.output
        assert not spawned_egg.exists()

    def test_delete_nonexistent(self, tmp_path: Path):
        result = runner.invoke(app, ["delete", str(tmp_path / "nope.egg")])
        assert result.exit_code == 1
        assert "Not found" in result.output


# ---------------------------------------------------------------------------
# keygen
# ---------------------------------------------------------------------------


class TestKeygenCommand:
    def test_keygen_writes_pem_pair(self, tmp_path: Path):
        key_dir = tmp_path / "mykeys"
        result = runner.invoke(app, ["keygen", "--dir", str(key_dir)])
        assert result.exit_code == 0
        assert "Keypair generated" in result.output
        assert (key_dir / "private.pem").exists()
        assert (key_dir / "public.pem").exists()


# ---------------------------------------------------------------------------
# push / pull / registry
# ---------------------------------------------------------------------------


class TestRegistryStubs:
    def test_push_no_registry_config(self, spawned_egg: Path):
        result = runner.invoke(
            app, ["push", str(spawned_egg), "--name", "user/test", "--version", "0.1.0"]
        )
        assert result.exit_code == 1
        assert "Registry not configured" in result.output

    def test_pull_no_registry_config(self):
        result = runner.invoke(app, ["pull", "user/test", "--version", "0.1.0"])
        assert result.exit_code == 1
        assert "Registry not configured" in result.output


# ---------------------------------------------------------------------------
# Error path tests
# ---------------------------------------------------------------------------


class TestErrorPaths:
    def test_spawn_invalid_agent_type(
        self, openclaw_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE nonexistent_type {openclaw_source}\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["spawn", "-o", str(tmp_path / "out.egg")])
        assert result.exit_code == 1

    def test_no_args_shows_help(self):
        result = runner.invoke(app, [])
        assert result.exit_code in (0, 2)
        assert "Usage" in result.output or "usage" in result.output.lower()


# ---------------------------------------------------------------------------
# Auth CLI commands
# ---------------------------------------------------------------------------


class TestAuthCLI:
    def test_auth_commands_require_registry_without_url(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("NYDUS_REGISTRY_URL", raising=False)
        for args in (
            ["register", "alice", "--password", "s3cret"],
            ["login", "alice", "--password", "s3cret"],
            ["logout"],
        ):
            result = runner.invoke(app, args)
            assert result.exit_code == 1
            assert "Registry not configured" in result.output

    def test_login_help(self):
        result = runner.invoke(app, ["login", "--help"])
        assert result.exit_code == 0
        assert "login" in result.output.lower() or "Log in" in result.output


# ---------------------------------------------------------------------------
# env
# ---------------------------------------------------------------------------


class TestEnvCommand:
    @pytest.fixture
    def egg_with_secrets(self, tmp_path: Path) -> Path:
        """Create an egg that has two SecretRecords."""
        from datetime import UTC, datetime

        from pynydus.api.schemas import (
            AgentSkill,
            Egg,
            Manifest,
            MemoryModule,
            MemoryRecord,
            SecretRecord,
            SecretsModule,
            SkillsModule,
        )
        from pynydus.common.enums import (
            AgentType,
            InjectionMode,
            MemoryLabel,
            SecretKind,
        )
        from pynydus.engine.packager import save

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.0.7",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
            ),
            skills=SkillsModule(
                skills=[
                    AgentSkill(
                        name="greet",
                        description="",
                        body="Say hello",
                        metadata={"id": "s1", "source_framework": "openclaw"},
                    ),
                ]
            ),
            memory=MemoryModule(
                memory=[
                    MemoryRecord(
                        id="m1",
                        text="I like Python",
                        label=MemoryLabel.PERSONA,
                        agent_type="openclaw",
                        source_store="SOUL.md",
                    ),
                ]
            ),
            secrets=SecretsModule(
                secrets=[
                    SecretRecord(
                        id="secret_001",
                        placeholder="{{SECRET_001}}",
                        kind=SecretKind.CREDENTIAL,
                        name="OPENAI_API_KEY",
                        required_at_hatch=True,
                        injection_mode=InjectionMode.ENV,
                        description="OpenAI API key for the agent runtime",
                    ),
                    SecretRecord(
                        id="pii_001",
                        placeholder="{{PII_001}}",
                        kind=SecretKind.PII,
                        pii_type="PERSON",
                        name="PII_PERSON_NAME",
                        required_at_hatch=False,
                        injection_mode=InjectionMode.SUBSTITUTION,
                        description="Redacted PERSON_NAME",
                    ),
                ]
            ),
        )
        egg_path = tmp_path / "secrets.egg"
        save(egg, egg_path)
        return egg_path

    def test_env_basic(self, egg_with_secrets: Path, tmp_path: Path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        env_path = sub / "custom.env"
        result = runner.invoke(app, ["env", str(egg_with_secrets), "-o", str(env_path)])
        assert result.exit_code == 0, result.output
        assert env_path.exists()
        content = env_path.read_text()
        assert "OPENAI_API_KEY=" in content
        assert "PII_PERSON_NAME=" in content
        assert "[credential]" in content
        assert "[pii]" in content
        assert "(required)" in content
        assert "(optional)" in content
        assert "Generated by nydus env" in content
        assert "2 secret(s)" in result.output

    def test_env_missing_egg(self, tmp_path: Path):
        result = runner.invoke(app, ["env", str(tmp_path / "nonexistent.egg")])
        assert result.exit_code == 1
        assert "Error" in result.output
