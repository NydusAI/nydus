"""Unit tests for the Python SDK (client/client.py).

Tests verify real client logic: model_copy for raw_artifacts/spawn_log,
sign flag forwarding, auto-version resolution.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pynydus import Nydus
from pynydus.api.errors import ConfigError
from pynydus.api.schemas import DiffReport, Egg, HatchResult, ValidationReport
from pynydus.common.enums import AgentType

from conftest import make_egg


@pytest.fixture
def nydus(monkeypatch: pytest.MonkeyPatch) -> Nydus:
    monkeypatch.delenv("NYDUS_LLM_TYPE", raising=False)
    monkeypatch.delenv("NYDUS_LLM_API_KEY", raising=False)
    monkeypatch.delenv("NYDUS_REGISTRY_URL", raising=False)
    return Nydus()


class TestSpawn:
    @patch("pynydus.engine.pipeline.spawn")
    @patch("pynydus.engine.nydusfile.parse_file")
    def test_spawn(self, mock_parse, mock_spawn, nydus, tmp_path):
        nf = tmp_path / "Nydusfile"
        nf.write_text("SOURCE openclaw ./src\n")
        from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective

        mock_parse.return_value = NydusfileConfig(
            sources=[SourceDirective(agent_type="openclaw", path="./src")]
        )
        egg = make_egg()
        raw = {"SOUL.md": "raw content"}
        log_entries = [{"type": "test"}]
        mock_spawn.return_value = (egg, raw, {"spawn_log": log_entries})
        result = nydus.spawn(nydusfile=nf)

        assert result.raw_artifacts == raw
        assert result.spawn_log == log_entries

    @patch("pynydus.engine.pipeline.spawn")
    @patch("pynydus.engine.nydusfile.resolve_nydusfile")
    @patch("pynydus.engine.nydusfile.parse_file")
    def test_discovers_nydusfile_in_cwd(
        self, mock_parse, mock_resolve, mock_spawn, nydus, tmp_path
    ):
        mock_resolve.return_value = tmp_path / "Nydusfile"
        from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective

        mock_parse.return_value = NydusfileConfig(
            sources=[SourceDirective(agent_type="openclaw", path="./src")]
        )
        mock_spawn.return_value = (make_egg(), {}, {"spawn_log": []})
        nydus.spawn()
        mock_resolve.assert_called_once()


class TestHatch:
    @patch("pynydus.engine.hatcher.hatch")
    def test_hatch(self, mock_hatch, nydus, tmp_path):
        mock_hatch.return_value = HatchResult(
            target=AgentType.OPENCLAW,
            output_dir=tmp_path,
            files_created=["SOUL.md"],
            warnings=[],
        )
        egg = make_egg()
        env = tmp_path / "agent.env"
        env.write_text("KEY=val\n")
        result = nydus.hatch(egg, target=AgentType.OPENCLAW, output_dir=tmp_path, secrets=str(env))
        assert mock_hatch.call_args[1]["secrets_path"] == Path(str(env))
        assert isinstance(result, HatchResult)


class TestSave:
    @patch("pynydus.engine.packager.save")
    def test_unsigned(self, mock_save, nydus, tmp_path):
        egg = make_egg()
        out = tmp_path / "test.egg"
        mock_save.return_value = out
        nydus.save(egg, out)
        assert mock_save.call_args[1]["private_key"] is None

    @patch("pynydus.security.signing.load_private_key")
    @patch("pynydus.engine.packager.save")
    def test_signed(self, mock_save, mock_key, nydus, tmp_path):
        mock_key.return_value = b"fake-key"
        out = tmp_path / "test.egg"
        mock_save.return_value = out
        nydus.save(make_egg(), out, sign=True)
        assert mock_save.call_args[1]["private_key"] == b"fake-key"


class TestLoad:
    @patch("pynydus.engine.packager.load")
    def test_load(self, mock_load, nydus, tmp_path):
        mock_load.return_value = make_egg()
        result = nydus.load(tmp_path / "test.egg")
        assert isinstance(result, Egg)


class TestPush:
    @patch("pynydus.engine.packager._unpack_egg_core")
    def test_auto_version(self, mock_unpack, monkeypatch):
        monkeypatch.setenv("NYDUS_REGISTRY_URL", "http://localhost:8000")
        monkeypatch.delenv("NYDUS_LLM_TYPE", raising=False)
        monkeypatch.delenv("NYDUS_LLM_API_KEY", raising=False)
        ny = Nydus()

        egg = make_egg()
        egg.manifest.egg_version = "1.2.3"
        mock_unpack.return_value = egg

        mock_client = MagicMock()
        mock_client.push.return_value = {"status": "ok"}
        with patch.object(ny, "_get_registry_client", return_value=mock_client):
            ny.push(Path("test.egg"), name="test/egg")
        assert mock_client.push.call_args[1]["version"] == "1.2.3"

    def test_no_registry(self, nydus, tmp_path):
        with pytest.raises(ConfigError, match="Registry not configured"):
            nydus.push(tmp_path / "test.egg", name="test/egg", version="0.1.0")


class TestValidateDiff:
    @patch("pynydus.engine.validator.validate_egg")
    def test_validate(self, mock_val, nydus):
        mock_val.return_value = ValidationReport(valid=True, issues=[])
        assert nydus.validate(make_egg()).valid

    @patch("pynydus.engine.differ.diff_eggs")
    def test_diff(self, mock_diff, nydus):
        mock_diff.return_value = DiffReport(identical=True, entries=[])
        egg = make_egg()
        assert nydus.diff(egg, egg).identical


class TestConfig:
    def test_llm_from_env(self, monkeypatch):
        monkeypatch.setenv("NYDUS_LLM_TYPE", "anthropic/claude-haiku-4-5-20251001")
        monkeypatch.setenv("NYDUS_LLM_API_KEY", "sk-test")
        ny = Nydus()
        assert ny._config.llm is not None

    def test_registry_from_env(self, monkeypatch):
        monkeypatch.setenv("NYDUS_REGISTRY_URL", "http://localhost:8000")
        monkeypatch.setenv("NYDUS_REGISTRY_AUTHOR", "tester")
        ny = Nydus()
        assert ny._config.registry is not None
