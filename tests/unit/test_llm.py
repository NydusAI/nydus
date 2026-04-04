"""Tests for the LLM abstraction layer (pynydus.llm + pynydus.config + engine/refinement.py)
and graceful degradation when LLM is unavailable."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from pynydus.cmd.main import app
from pynydus.config import NydusConfig, load_config
from pynydus.llm import LLMTierConfig, create_client, create_completion
from typer.testing import CliRunner

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tier_config() -> LLMTierConfig:
    return LLMTierConfig(
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        api_key="sk-ant-test-key-123",
    )


# ---------------------------------------------------------------------------
# LLMTierConfig validation
# ---------------------------------------------------------------------------


class TestLLMTierConfig:
    def test_requires_provider(self):
        with pytest.raises(ValidationError):
            LLMTierConfig(model="gpt-4o", api_key="sk-test")  # type: ignore[call-arg]

    def test_requires_model(self):
        with pytest.raises(ValidationError):
            LLMTierConfig(provider="openai", api_key="sk-test")  # type: ignore[call-arg]

    def test_requires_api_key(self):
        with pytest.raises(ValidationError):
            LLMTierConfig(provider="openai", model="gpt-4o")  # type: ignore[call-arg]

    def test_accepts_valid(self, tier_config: LLMTierConfig):
        assert tier_config.provider == "anthropic"
        assert tier_config.model == "claude-haiku-4-5-20251001"
        assert tier_config.api_key == "sk-ant-test-key-123"

    def test_no_extra_fields_allowed_by_default(self):
        """Fields not in the schema should be ignored (Pydantic default)."""
        cfg = LLMTierConfig(provider="openai", model="gpt-4o", api_key="sk-test", extra="ignored")
        assert not hasattr(cfg, "extra") or cfg.model_fields_set == {"provider", "model", "api_key"}


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


class TestCreateClient:
    @patch("pynydus.llm.client.instructor.from_provider")
    def test_calls_instructor_with_correct_args(
        self, mock_from_provider: MagicMock, tier_config: LLMTierConfig
    ):
        mock_from_provider.return_value = MagicMock()
        client = create_client(tier_config)

        mock_from_provider.assert_called_once_with(
            "anthropic/claude-haiku-4-5-20251001",
            api_key="sk-ant-test-key-123",
        )
        assert client is mock_from_provider.return_value

    @patch("pynydus.llm.client.instructor.from_provider")
    def test_openai_provider_format(self, mock_from_provider: MagicMock):
        tier = LLMTierConfig(provider="openai", model="gpt-4o", api_key="sk-test")
        create_client(tier)
        mock_from_provider.assert_called_once_with(
            "openai/gpt-4o",
            api_key="sk-test",
        )


# ---------------------------------------------------------------------------
# create_completion
# ---------------------------------------------------------------------------


class TestCreateCompletion:
    @patch("pynydus.llm.client.create_client")
    def test_calls_client_create(self, mock_create_client: MagicMock):
        from pydantic import BaseModel

        class Output(BaseModel):
            answer: str

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = Output(answer="42")
        mock_create_client.return_value = mock_client

        tier = LLMTierConfig(provider="openai", model="gpt-4o", api_key="sk-test")
        result = create_completion(
            tier,
            messages=[{"role": "user", "content": "What is 6*7?"}],
            response_model=Output,
        )

        assert result.answer == "42"
        mock_client.chat.completions.create.assert_called_once_with(
            response_model=Output,
            messages=[{"role": "user", "content": "What is 6*7?"}],
            max_retries=3,
        )

    @patch("pynydus.llm.client.create_client")
    def test_custom_max_retries(self, mock_create_client: MagicMock):
        from pydantic import BaseModel

        class Output(BaseModel):
            answer: str

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = Output(answer="ok")
        mock_create_client.return_value = mock_client

        tier = LLMTierConfig(provider="openai", model="gpt-4o", api_key="sk-test")
        create_completion(
            tier,
            messages=[{"role": "user", "content": "hi"}],
            response_model=Output,
            max_retries=5,
        )

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_retries"] == 5


# ---------------------------------------------------------------------------
# Unified config loading (pynydus.config)
# ---------------------------------------------------------------------------


class TestNydusConfig:
    def test_empty_config_is_valid(self):
        """All sections are optional."""
        cfg = NydusConfig()
        assert cfg.llm is None

    def test_with_llm_section(self, llm_config: LLMTierConfig):
        cfg = NydusConfig(llm=llm_config)
        assert cfg.llm is not None
        assert cfg.llm.provider == "anthropic"


class TestLoadConfig:
    def test_empty_env_no_llm_no_registry(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("NYDUS_LLM_TYPE", raising=False)
        monkeypatch.delenv("NYDUS_LLM_API_KEY", raising=False)
        monkeypatch.delenv("NYDUS_REGISTRY_URL", raising=False)
        monkeypatch.delenv("NYDUS_REGISTRY_AUTHOR", raising=False)
        cfg = load_config()
        assert cfg.llm is None
        assert cfg.registry is None

    def test_llm_from_type_and_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NYDUS_LLM_TYPE", "anthropic/claude-3-haiku")
        monkeypatch.setenv("NYDUS_LLM_API_KEY", "sk-test")
        cfg = load_config()
        assert cfg.llm is not None
        assert cfg.llm.provider == "anthropic"
        assert cfg.llm.model == "claude-3-haiku"
        assert cfg.llm.api_key == "sk-test"

    def test_partial_type_without_key_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("NYDUS_LLM_API_KEY", raising=False)
        monkeypatch.setenv("NYDUS_LLM_TYPE", "anthropic/claude-3-haiku")
        with pytest.raises(ValueError, match="both be set"):
            load_config()

    def test_partial_key_without_type_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("NYDUS_LLM_TYPE", raising=False)
        monkeypatch.setenv("NYDUS_LLM_API_KEY", "sk-test")
        with pytest.raises(ValueError, match="both be set"):
            load_config()

    def test_invalid_llm_type_format_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NYDUS_LLM_TYPE", "anthropic")
        monkeypatch.setenv("NYDUS_LLM_API_KEY", "sk-test")
        with pytest.raises(ValueError, match="provider/model"):
            load_config()

    def test_registry_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NYDUS_REGISTRY_URL", "http://nest.example.com")
        monkeypatch.setenv("NYDUS_REGISTRY_AUTHOR", "jae")
        cfg = load_config()
        assert cfg.registry is not None
        assert cfg.registry.url == "http://nest.example.com"
        assert cfg.registry.author == "jae"

    def test_registry_url_only(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NYDUS_REGISTRY_URL", "http://localhost:8000")
        monkeypatch.delenv("NYDUS_REGISTRY_AUTHOR", raising=False)
        cfg = load_config()
        assert cfg.registry is not None
        assert cfg.registry.author is None


# ---------------------------------------------------------------------------
# Pipeline integration — spawn/hatch still work without llm_config
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    @pytest.fixture
    def openclaw_project(self, tmp_path: Path) -> Path:
        src = tmp_path / "source"
        src.mkdir()
        (src / "soul.md").write_text("I am a helpful assistant.\n")
        (src / "knowledge.md").write_text("The sky is blue.\n")
        (src / "skill.md").write_text("# Research\nDo research.\n")
        return src

    def _oc_config(self, project: Path):
        from helpers import config_for

        return config_for("openclaw", project)

    @patch("pynydus.engine.refinement.refine_memory")
    @patch("pynydus.engine.refinement.refine_skills")
    def test_spawn_with_llm_config_calls_refinement(
        self,
        mock_refine_skills: MagicMock,
        mock_refine_memory: MagicMock,
        openclaw_project: Path,
        llm_config: LLMTierConfig,
    ):
        """When llm_config is provided, refine_skills and refine_memory are called."""
        from pynydus.engine.pipeline import spawn

        mock_refine_skills.side_effect = lambda skills, cfg, **kw: skills
        mock_refine_memory.side_effect = lambda memory, cfg, **kw: memory

        config = self._oc_config(openclaw_project)
        egg, _, _logs = spawn(
            config,
            nydusfile_dir=openclaw_project.parent,
            llm_config=llm_config,
        )

        mock_refine_skills.assert_called_once()
        mock_refine_memory.assert_called_once()
        assert mock_refine_skills.call_args[0][1] is llm_config
        assert mock_refine_memory.call_args[0][1] is llm_config

    @patch("pynydus.engine.refinement.refine_hatch")
    def test_hatch_with_llm_config_calls_refinement(
        self,
        mock_refine: MagicMock,
        openclaw_project: Path,
        tmp_path: Path,
        llm_config: LLMTierConfig,
    ):
        """When llm_config is provided, refine_hatch is called."""
        from pynydus.engine.hatcher import hatch
        from pynydus.engine.pipeline import spawn

        mock_refine.side_effect = lambda result, egg, llm_cfg, **kwargs: result

        config = self._oc_config(openclaw_project)
        egg, _, _logs = spawn(config, nydusfile_dir=openclaw_project.parent)
        out = tmp_path / "hatched"
        hatch(
            egg,
            target="openclaw",
            output_dir=out,
            llm_config=llm_config,
            mode="rebuild",
        )

        mock_refine.assert_called_once()
        call_args = mock_refine.call_args
        assert call_args[0][2] is llm_config


# ---------------------------------------------------------------------------
# CLI: LLM optional / graceful (no duplicate client or hatch CLI coverage)
# ---------------------------------------------------------------------------


class TestLLMGracefulCLI:
    def test_spawn_succeeds_without_llm_env(
        self, openclaw_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_project}\n")
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "out.egg"
        result = runner.invoke(app, ["spawn", "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()

    @patch("pynydus.llm.client.create_client", side_effect=RuntimeError("LLM down"))
    def test_spawn_succeeds_when_create_client_raises(
        self, _mock_client, openclaw_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_project}\n")
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "out.egg"
        result = runner.invoke(app, ["spawn", "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_no_deprecated_no_llm_flags_in_help(self):
        for cmd in ("spawn", "hatch"):
            result = runner.invoke(app, [cmd, "--help"])
            assert "--no-llm" not in result.output
