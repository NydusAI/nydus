"""CLI integration tests (Priority 4.1).

Uses typer.testing.CliRunner to exercise each CLI command end-to-end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pynydus.cmd.main import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def openclaw_source(tmp_path: Path) -> Path:
    """Create a minimal OpenClaw source directory."""
    (tmp_path / "soul.md").write_text("# Soul\nI am a helpful AI assistant.")
    (tmp_path / "knowledge.md").write_text("# Knowledge\nPython is a language.")
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

    def test_spawn_no_nydusfile(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["spawn", "-o", str(tmp_path / "out.egg")])
        assert result.exit_code == 1
        assert "No Nydusfile found" in result.output

    def test_spawn_with_purpose(
        self, openclaw_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(
            f'SOURCE openclaw {openclaw_source}\nPURPOSE "test agent"\n'
        )
        monkeypatch.chdir(tmp_path)
        egg_path = tmp_path / "out.egg"
        result = runner.invoke(app, ["spawn", "-o", str(egg_path)])
        assert result.exit_code == 0
        assert egg_path.exists()

    def test_spawn_with_redact_none(
        self, openclaw_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_source}\nREDACT none\n")
        monkeypatch.chdir(tmp_path)
        egg_path = tmp_path / "out.egg"
        result = runner.invoke(app, ["spawn", "-o", str(egg_path)])
        assert result.exit_code == 0

    def test_spawn_shows_counts(
        self, openclaw_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_source}\n")
        monkeypatch.chdir(tmp_path)
        egg_path = tmp_path / "out.egg"
        result = runner.invoke(app, ["spawn", "-o", str(egg_path)])
        assert result.exit_code == 0
        assert "skills=" in result.output
        assert "memory=" in result.output
        assert "secrets=" in result.output

    def test_spawn_unsigned_message(
        self, openclaw_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_source}\n")
        monkeypatch.chdir(tmp_path)
        egg_path = tmp_path / "out.egg"
        result = runner.invoke(app, ["spawn", "-o", str(egg_path)])
        assert result.exit_code == 0
        assert "unsigned" in result.output


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

    def test_hatch_with_reconstruct(self, spawned_egg: Path, tmp_path: Path):
        out_dir = tmp_path / "hatched"
        result = runner.invoke(
            app,
            [
                "hatch",
                str(spawned_egg),
                "--target",
                "openclaw",
                "--reconstruct",
                "-o",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


class TestInspectCommand:
    def test_inspect_basic(self, spawned_egg: Path):
        result = runner.invoke(app, ["inspect", str(spawned_egg)])
        assert result.exit_code == 0
        assert "Egg:" in result.output
        assert "nydus" in result.output
        assert "source: openclaw" in result.output.lower() or "openclaw" in result.output

    def test_inspect_with_secrets(self, spawned_egg: Path):
        result = runner.invoke(app, ["inspect", str(spawned_egg), "--secrets"])
        assert result.exit_code == 0

    def test_inspect_with_logs(self, spawned_egg: Path):
        result = runner.invoke(app, ["inspect", str(spawned_egg), "--logs"])
        assert result.exit_code == 0

    def test_inspect_missing_egg(self, tmp_path: Path):
        result = runner.invoke(app, ["inspect", str(tmp_path / "nope.egg")])
        assert result.exit_code == 1
        assert "Error" in result.output


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


class TestValidateCommand:
    def test_validate_valid_egg(self, spawned_egg: Path):
        result = runner.invoke(app, ["validate", str(spawned_egg)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_missing_egg(self, tmp_path: Path):
        result = runner.invoke(app, ["validate", str(tmp_path / "nope.egg")])
        assert result.exit_code == 1

    def test_validate_corrupted_egg(self, tmp_path: Path):
        bad_egg = tmp_path / "bad.egg"
        bad_egg.write_text("not a real egg")
        result = runner.invoke(app, ["validate", str(bad_egg)])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


class TestDiffCommand:
    def test_diff_identical(self, spawned_egg: Path, tmp_path: Path):
        # Spawn a second identical egg
        egg2 = tmp_path / "test2.egg"
        # Copy the egg
        import shutil

        shutil.copy(spawned_egg, egg2)
        result = runner.invoke(app, ["diff", str(spawned_egg), str(egg2)])
        assert result.exit_code == 0
        assert "identical" in result.output.lower()

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
        result = runner.invoke(
            app, ["diff", str(spawned_egg), str(tmp_path / "nope.egg")]
        )
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
    def test_keygen_default_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        key_dir = tmp_path / ".nydus" / "keys"
        monkeypatch.setenv("HOME", str(tmp_path))
        result = runner.invoke(app, ["keygen", "--dir", str(key_dir)])
        assert result.exit_code == 0
        assert "Keypair generated" in result.output
        assert (key_dir / "private.pem").exists()
        assert (key_dir / "public.pem").exists()

    def test_keygen_custom_dir(self, tmp_path: Path):
        key_dir = tmp_path / "mykeys"
        result = runner.invoke(app, ["keygen", "--dir", str(key_dir)])
        assert result.exit_code == 0
        assert (key_dir / "private.pem").exists()


# ---------------------------------------------------------------------------
# push / pull (Phase 1b stubs)
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
    def test_spawn_invalid_source_type(
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
    """Test register, login, logout commands."""

    def test_register_requires_registry_config(self, tmp_path: Path):
        cfg = tmp_path / "config.json"
        cfg.write_text("{}")
        result = runner.invoke(
            app,
            ["register", "alice", "--password", "s3cret", "--config", str(cfg)],
        )
        assert result.exit_code == 1
        assert "Registry not configured" in result.output

    def test_login_requires_registry_config(self, tmp_path: Path):
        cfg = tmp_path / "config.json"
        cfg.write_text("{}")
        result = runner.invoke(
            app,
            ["login", "alice", "--password", "s3cret", "--config", str(cfg)],
        )
        assert result.exit_code == 1
        assert "Registry not configured" in result.output

    def test_logout_requires_registry_config(self, tmp_path: Path):
        cfg = tmp_path / "config.json"
        cfg.write_text("{}")
        result = runner.invoke(
            app,
            ["logout", "--config", str(cfg)],
        )
        assert result.exit_code == 1
        assert "Registry not configured" in result.output

    def test_register_help(self):
        result = runner.invoke(app, ["register", "--help"])
        assert result.exit_code == 0
        assert "register" in result.output.lower() or "Register" in result.output

    def test_login_help(self):
        result = runner.invoke(app, ["login", "--help"])
        assert result.exit_code == 0
        assert "login" in result.output.lower() or "Log in" in result.output

    def test_logout_help(self):
        result = runner.invoke(app, ["logout", "--help"])
        assert result.exit_code == 0
        assert "logout" in result.output.lower() or "Log out" in result.output


# ---------------------------------------------------------------------------
# env
# ---------------------------------------------------------------------------


class TestEnvCommand:
    @pytest.fixture
    def egg_with_secrets(self, tmp_path: Path) -> Path:
        """Create an egg that has two SecretRecords."""
        from datetime import UTC, datetime

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
        from pynydus.engine.packager import pack

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["skills", "memory", "secrets"],
            ),
            skills=SkillsModule(skills=[
                SkillRecord(id="s1", name="greet", source_type="openclaw", content="Say hello"),
            ]),
            memory=MemoryModule(memory=[
                MemoryRecord(
                    id="m1", text="I like Python", label=MemoryLabel.PERSONA,
                    source_framework="openclaw", source_store="soul.md",
                ),
            ]),
            secrets=SecretsModule(secrets=[
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
            ]),
        )
        egg_path = tmp_path / "secrets.egg"
        pack(egg, egg_path)
        return egg_path

    def test_env_basic(self, egg_with_secrets: Path, tmp_path: Path):
        env_path = tmp_path / "hatch.env"
        result = runner.invoke(
            app, ["env", str(egg_with_secrets), "-o", str(env_path)]
        )
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

    def test_env_no_secrets(self, spawned_egg: Path, tmp_path: Path):
        env_path = tmp_path / "hatch.env"
        result = runner.invoke(
            app, ["env", str(spawned_egg), "-o", str(env_path)]
        )
        assert result.exit_code == 0
        assert "No secrets" in result.output
        assert not env_path.exists()

    def test_env_missing_egg(self, tmp_path: Path):
        result = runner.invoke(
            app, ["env", str(tmp_path / "nonexistent.egg")]
        )
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_env_custom_output(self, egg_with_secrets: Path, tmp_path: Path):
        custom_path = tmp_path / "subdir" / "custom.env"
        result = runner.invoke(
            app, ["env", str(egg_with_secrets), "-o", str(custom_path)]
        )
        assert result.exit_code == 0, result.output
        assert custom_path.exists()
        assert "2 secret(s)" in result.output
