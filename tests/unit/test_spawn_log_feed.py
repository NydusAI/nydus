"""Tests for feeding spawn log to hatch LLM.

Verifies that the full spawn log is serialized as JSON and included
in the hatch refinement prompt (not a lossy summary).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from pynydus.api.schemas import Egg
from pynydus.engine.refinement import refine_hatch
from pynydus.llm import LLMTierConfig


class TestSpawnLogInHatchPrompt:
    @patch("pynydus.engine.refinement.create_completion")
    def test_full_log_in_prompt(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = None
        spawn_log = [
            {"type": "pipeline_start", "redact": True, "sources": ["./openclaw"]},
            {"type": "source_files_read", "files": ["SOUL.md"], "count": 1},
            {"type": "secret_scan", "tool": "gitleaks", "name": "API_KEY"},
        ]
        file_dict = {"SOUL.md": "Hello"}

        refine_hatch(file_dict, minimal_egg, llm_config, spawn_log=spawn_log)

        user_msg = mock_completion.call_args[1]["messages"][1]["content"]
        assert "Spawn log:" in user_msg
        assert '"pipeline_start"' in user_msg
        assert '"source_files_read"' in user_msg
        assert '"secret_scan"' in user_msg

    @patch("pynydus.engine.refinement.create_completion")
    def test_empty_log_no_block(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = None
        file_dict = {"SOUL.md": "Hello"}

        refine_hatch(file_dict, minimal_egg, llm_config, spawn_log=[])

        user_msg = mock_completion.call_args[1]["messages"][1]["content"]
        assert "Spawn log:" not in user_msg

    @patch("pynydus.engine.refinement.create_completion")
    def test_log_is_valid_json_in_prompt(
        self,
        mock_completion: MagicMock,
        minimal_egg: Egg,
        llm_config: LLMTierConfig,
    ):
        mock_completion.return_value = None
        spawn_log = [
            {"type": "records_built", "memory": [{"id": "mem_001", "label": "persona"}]},
        ]
        file_dict = {"SOUL.md": "Hello"}

        refine_hatch(file_dict, minimal_egg, llm_config, spawn_log=spawn_log)

        user_msg = mock_completion.call_args[1]["messages"][1]["content"]
        start = user_msg.index("Spawn log:\n") + len("Spawn log:\n")
        end = user_msg.index("\n\n", start)
        embedded_json = user_msg[start:end]
        parsed = json.loads(embedded_json)
        assert parsed[0]["type"] == "records_built"
