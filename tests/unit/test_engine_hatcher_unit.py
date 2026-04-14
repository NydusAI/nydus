"""Unit tests for the hatch pipeline (engine/hatcher.py).

Assertions check written file content, not mock call counts.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pynydus.api.errors import HatchError
from pynydus.api.raw_types import RenderResult
from pynydus.common.enums import AgentType, HatchMode

from conftest import make_egg


@pytest.fixture
def _mock_render():
    """Patch _get_hatcher to return a mock that renders a single file."""
    with patch("pynydus.engine.hatcher._get_hatcher") as mock_get:
        mock_hatcher = MagicMock()
        mock_hatcher.render.return_value = RenderResult(
            files={"SOUL.md": "original content\n"}, warnings=[]
        )
        mock_get.return_value = mock_hatcher
        yield mock_hatcher


class TestRebuildMode:
    def test_dispatch(self, _mock_render, tmp_path: Path):
        from pynydus.engine.hatcher import hatch

        egg = make_egg()
        result = hatch(egg, target=AgentType.OPENCLAW, output_dir=tmp_path / "out")
        assert "SOUL.md" in result.files_created
        assert (tmp_path / "out" / "SOUL.md").read_text() == "original content\n"


class TestPassthroughMode:
    def test_raw_artifacts(self, tmp_path: Path):
        from pynydus.engine.hatcher import hatch

        egg = make_egg()
        raw = {"SOUL.md": "raw content"}
        hatch(
            egg,
            target=AgentType.OPENCLAW,
            output_dir=tmp_path / "out",
            mode=HatchMode.PASSTHROUGH,
            raw_artifacts=raw,
        )
        assert (tmp_path / "out" / "SOUL.md").read_text() == "raw content"

    def test_mismatch_rejected(self, tmp_path: Path):
        from pynydus.engine.hatcher import hatch

        egg = make_egg(agent_type=AgentType.OPENCLAW)
        with pytest.raises(HatchError, match="passthrough"):
            hatch(
                egg,
                target=AgentType.LETTA,
                output_dir=tmp_path / "out",
                mode=HatchMode.PASSTHROUGH,
                raw_artifacts={"a.md": "x"},
            )


class TestVersionCompat:
    def test_old_egg_rejected(self, tmp_path: Path):
        from pynydus.engine.hatcher import hatch

        egg = make_egg(min_nydus_version="99.0.0")
        with pytest.raises(HatchError, match="nydus >= 99.0.0"):
            hatch(egg, target=AgentType.OPENCLAW, output_dir=tmp_path / "out")


class TestSecretInjection:
    def test_secrets_from_env(self, _mock_render, tmp_path: Path):
        from pynydus.api.schemas import SecretRecord, SecretsModule
        from pynydus.common.enums import InjectionMode, SecretKind
        from pynydus.engine.hatcher import hatch

        _mock_render.render.return_value = RenderResult(
            files={"config.json": '{"key": "{{SECRET_001}}"}\n'}, warnings=[]
        )

        egg = make_egg()
        egg.secrets = SecretsModule(
            secrets=[
                SecretRecord(
                    id="s1",
                    placeholder="{{SECRET_001}}",
                    kind=SecretKind.CREDENTIAL,
                    name="API_KEY",
                    required_at_hatch=True,
                    injection_mode=InjectionMode.ENV,
                )
            ]
        )

        env_file = tmp_path / "agent.env"
        env_file.write_text("API_KEY=real-value\n")

        out = tmp_path / "out"
        hatch(egg, target=AgentType.OPENCLAW, output_dir=out, secrets_path=env_file)
        config_content = (out / "config.json").read_text()
        assert "real-value" in config_content
        assert "{{SECRET_001}}" not in config_content


class TestLLMRefinementHatch:
    @patch("pynydus.engine.refinement.refine_hatch")
    def test_with_llm(self, mock_refine, _mock_render, tmp_path: Path):
        from pynydus.engine.hatcher import hatch
        from pynydus.llm import LLMTierConfig

        mock_refine.side_effect = lambda fd, egg, cfg, **kw: {
            k: v.replace("original", "refined") for k, v in fd.items()
        }

        tier = LLMTierConfig(provider="openai", model="gpt-4o", api_key="sk-test")
        egg = make_egg()
        out = tmp_path / "out"
        hatch(egg, target=AgentType.OPENCLAW, output_dir=out, llm_config=tier)
        assert "refined content" in (out / "SOUL.md").read_text()

    def test_without_llm(self, _mock_render, tmp_path: Path):
        from pynydus.engine.hatcher import hatch

        egg = make_egg()
        out = tmp_path / "out"
        hatch(egg, target=AgentType.OPENCLAW, output_dir=out)
        assert "original content" in (out / "SOUL.md").read_text()


class TestHatchLog:
    def test_log_written(self, _mock_render, tmp_path: Path):
        from pynydus.engine.hatcher import hatch

        egg = make_egg()
        out = tmp_path / "out"
        hatch(egg, target=AgentType.OPENCLAW, output_dir=out)
        assert (out / "logs" / "hatch_log.json").exists()
