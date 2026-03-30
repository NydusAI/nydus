"""Tests for the LLM abstraction layer (pkg/llm.py + pkg/config.py + engine/refinement.py)
and graceful degradation when LLM is unavailable."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from pynydus.cmd.main import app
from pynydus.pkg.config import NydusConfig, load_config
from pynydus.pkg.llm import (
    LLMTierConfig,
    NydusLLMConfig,
    create_client,
    create_completion,
)

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


@pytest.fixture
def config_json(tmp_path: Path) -> Path:
    """Write a valid unified config JSON file."""
    data = {
        "llm": {
            "simple": {
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "api_key": "sk-ant-test",
            },
            "complex": {
                "provider": "openai",
                "model": "gpt-4o",
                "api_key": "sk-openai-test",
            },
        }
    }
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data))
    return p


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
        cfg = LLMTierConfig(
            provider="openai", model="gpt-4o", api_key="sk-test", extra="ignored"
        )
        assert not hasattr(cfg, "extra") or cfg.model_fields_set == {
            "provider", "model", "api_key"
        }


# ---------------------------------------------------------------------------
# NydusLLMConfig validation
# ---------------------------------------------------------------------------


class TestNydusLLMConfig:
    def test_requires_simple_tier(self, tier_config: LLMTierConfig):
        with pytest.raises(ValidationError):
            NydusLLMConfig(complex=tier_config)  # type: ignore[call-arg]

    def test_requires_complex_tier(self, tier_config: LLMTierConfig):
        with pytest.raises(ValidationError):
            NydusLLMConfig(simple=tier_config)  # type: ignore[call-arg]

    def test_requires_both_tiers(self):
        with pytest.raises(ValidationError):
            NydusLLMConfig()  # type: ignore[call-arg]

    def test_accepts_valid(self, llm_config: NydusLLMConfig):
        assert llm_config.simple.provider == "anthropic"
        assert llm_config.complex.provider == "openai"

    def test_mixed_providers(self):
        """The whole point: different providers per tier."""
        cfg = NydusLLMConfig(
            simple=LLMTierConfig(
                provider="anthropic", model="claude-haiku-4-5-20251001", api_key="sk-ant-x"
            ),
            complex=LLMTierConfig(
                provider="openai", model="gpt-4o", api_key="sk-openai-y"
            ),
        )
        assert cfg.simple.provider == "anthropic"
        assert cfg.complex.provider == "openai"


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


class TestCreateClient:
    @patch("pynydus.pkg.llm.instructor.from_provider")
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

    @patch("pynydus.pkg.llm.instructor.from_provider")
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
    @patch("pynydus.pkg.llm.create_client")
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

    @patch("pynydus.pkg.llm.create_client")
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
# Unified config loading (pkg/config.py)
# ---------------------------------------------------------------------------


class TestNydusConfig:
    def test_empty_config_is_valid(self):
        """All sections are optional."""
        cfg = NydusConfig()
        assert cfg.llm is None

    def test_with_llm_section(self, llm_config: NydusLLMConfig):
        cfg = NydusConfig(llm=llm_config)
        assert cfg.llm is not None
        assert cfg.llm.simple.provider == "anthropic"


class TestLoadConfig:
    def test_loads_valid_json(self, config_json: Path):
        cfg = load_config(config_json)
        assert cfg.llm is not None
        assert cfg.llm.simple.provider == "anthropic"
        assert cfg.llm.simple.model == "claude-haiku-4-5-20251001"
        assert cfg.llm.complex.provider == "openai"
        assert cfg.llm.complex.model == "gpt-4o"

    def test_explicit_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_config(tmp_path / "nonexistent.json")

    def test_default_missing_returns_empty(self, tmp_path: Path):
        """When no explicit path and default doesn't exist, return empty config."""
        with patch.object(Path, "cwd", return_value=tmp_path):
            cfg = load_config()
            assert cfg.llm is None

    def test_invalid_json(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_config(p)

    def test_invalid_schema(self, tmp_path: Path):
        p = tmp_path / "bad-schema.json"
        p.write_text(json.dumps({"llm": {"simple": {"provider": "openai"}}}))
        with pytest.raises(ValueError, match="Invalid config"):
            load_config(p)

    def test_empty_object_is_valid(self, tmp_path: Path):
        """Empty JSON object → empty NydusConfig (all sections None)."""
        p = tmp_path / "empty.json"
        p.write_text("{}")
        cfg = load_config(p)
        assert cfg.llm is None

    def test_llm_only_config(self, tmp_path: Path):
        """Config with only LLM section."""
        data = {
            "llm": {
                "simple": {
                    "provider": "anthropic",
                    "model": "claude-haiku-4-5-20251001",
                    "api_key": "sk-ant-test",
                },
                "complex": {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-6",
                    "api_key": "sk-ant-test",
                },
            }
        }
        p = tmp_path / "config.json"
        p.write_text(json.dumps(data))
        cfg = load_config(p)
        assert cfg.llm is not None
        assert cfg.llm.simple.model == "claude-haiku-4-5-20251001"
        assert cfg.llm.complex.model == "claude-sonnet-4-6"

    def test_auto_loads_default_path(self, tmp_path: Path):
        """When default config exists and no explicit path, loads it."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "llm": {
                "simple": {"provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-x"},
                "complex": {"provider": "openai", "model": "gpt-4o", "api_key": "sk-y"},
            }
        }))
        with patch.object(Path, "cwd", return_value=tmp_path):
            cfg = load_config()
            assert cfg.llm is not None
            assert cfg.llm.simple.model == "gpt-4o-mini"


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

    def test_spawn_without_llm_config(self, openclaw_project: Path):
        """Regression: spawn works exactly as before when llm_config is None."""
        from pynydus.engine.pipeline import build as spawn

        egg, raw, _logs = spawn(openclaw_project, source_type="openclaw")
        assert len(egg.skills.skills) >= 1
        assert len(egg.memory.memory) >= 1

    def test_hatch_without_llm_config(self, openclaw_project: Path, tmp_path: Path):
        """Regression: hatch works exactly as before when llm_config is None."""
        from pynydus.engine.hatcher import hatch
        from pynydus.engine.pipeline import build as spawn

        egg, _, _logs = spawn(openclaw_project, source_type="openclaw")
        out = tmp_path / "hatched"
        result = hatch(egg, target="openclaw", output_dir=out)
        assert len(result.files_created) > 0

    @patch("pynydus.engine.refinement.refine_memory")
    @patch("pynydus.engine.refinement.refine_skills")
    def test_spawn_with_llm_config_calls_refinement(
        self,
        mock_refine_skills: MagicMock,
        mock_refine_memory: MagicMock,
        openclaw_project: Path,
        llm_config: NydusLLMConfig,
    ):
        """When llm_config is provided, refine_skills and refine_memory are called."""
        from pynydus.engine.pipeline import build as spawn

        mock_refine_skills.side_effect = lambda skills, cfg, **kw: skills
        mock_refine_memory.side_effect = lambda memory, cfg, **kw: memory

        egg, _, _logs = spawn(
            openclaw_project,
            source_type="openclaw",
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
        llm_config: NydusLLMConfig,
    ):
        """When llm_config is provided, refine_hatch is called."""
        from pynydus.engine.hatcher import hatch
        from pynydus.engine.pipeline import build as spawn

        # Make the mock return its input (pass-through)
        mock_refine.side_effect = lambda result, egg, cfg, **kwargs: result

        egg, _, _logs = spawn(openclaw_project, source_type="openclaw")
        out = tmp_path / "hatched"
        result = hatch(
            egg, target="openclaw", output_dir=out,
            llm_config=llm_config, reconstruct=True,
        )

        mock_refine.assert_called_once()
        call_args = mock_refine.call_args
        assert call_args[0][2] is llm_config  # third arg is the config


# ---------------------------------------------------------------------------
# CLI graceful degradation (merged from test_no_llm_flag.py)
# ---------------------------------------------------------------------------


class TestSpawnGracefulDegradation:
    def test_spawn_succeeds_without_llm_config(
        self, openclaw_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Spawn works when no LLM config is present (no config.json)."""
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_project}\n")
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "out.egg"
        result = runner.invoke(app, ["spawn", "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert out.stat().st_size > 0

    @patch("pynydus.pkg.llm.create_client", side_effect=RuntimeError("LLM down"))
    def test_spawn_succeeds_when_llm_raises(
        self, _mock_client, openclaw_project: Path, tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch
    ):
        """Spawn still produces a valid egg when the LLM raises an exception."""
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_project}\n")
        monkeypatch.chdir(tmp_path)
        out = tmp_path / "out.egg"
        result = runner.invoke(app, ["spawn", "-o", str(out)])
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_no_llm_flag_removed_from_spawn(self):
        """The --no-llm flag should no longer be accepted by spawn."""
        result = runner.invoke(app, ["spawn", "--help"])
        assert "--no-llm" not in result.output


class TestHatchGracefulDegradation:
    def test_hatch_succeeds_without_llm_config(
        self, openclaw_project: Path, tmp_path: Path
    ):
        """Hatch works when no LLM config is present."""
        from pynydus.engine.packager import pack_with_raw
        from pynydus.engine.pipeline import build as engine_spawn

        egg, raw, logs = engine_spawn(openclaw_project, source_type="openclaw")
        egg_path = tmp_path / "test.egg"
        pack_with_raw(egg, egg_path, raw, spawn_log=logs.get("spawn_log"))

        out_dir = tmp_path / "hatched"
        result = runner.invoke(
            app,
            ["hatch", str(egg_path), "--target", "openclaw", "-o", str(out_dir)],
        )
        assert result.exit_code == 0, result.output

    def test_no_llm_flag_removed_from_hatch(self):
        """The --no-llm flag should no longer be accepted by hatch."""
        result = runner.invoke(app, ["hatch", "--help"])
        assert "--no-llm" not in result.output


class TestClientGracefulDegradation:
    def test_spawn_without_llm_config(self, openclaw_project: Path, tmp_path: Path):
        """Client.spawn() works without any LLM config."""
        from pynydus.client.client import Nydus

        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_project}\n")
        nydus = Nydus()
        egg = nydus.spawn(nydusfile=nydusfile)
        assert egg is not None
        assert len(egg.memory.memory) >= 1

    @patch("pynydus.pkg.llm.create_client", side_effect=ConnectionError("no network"))
    def test_spawn_degrades_gracefully_on_llm_error(
        self, _mock_client, openclaw_project: Path, tmp_path: Path
    ):
        """Client.spawn() succeeds even when LLM calls fail."""
        from pynydus.client.client import Nydus

        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_project}\n")
        nydus = Nydus()
        egg = nydus.spawn(nydusfile=nydusfile)
        assert egg is not None

    def test_hatch_without_llm_config(self, openclaw_project: Path, tmp_path: Path):
        """Client.hatch() works without any LLM config."""
        from pynydus.client.client import Nydus

        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {openclaw_project}\n")
        nydus = Nydus()
        egg = nydus.spawn(nydusfile=nydusfile)
        out_dir = tmp_path / "hatched"
        result = nydus.hatch(egg, target="openclaw", output_dir=out_dir)
        assert result.output_dir == out_dir


