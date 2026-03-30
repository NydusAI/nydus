"""Tests for `nydus inspect --logs` CLI flag."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from pynydus.api.schemas import Egg
from pynydus.cmd.main import app
from pynydus.engine.packager import pack_with_raw

runner = CliRunner()


class TestInspectLogs:
    def test_no_logs_flag_omits_log_output(self, sample_egg: Egg, tmp_path: Path):
        """Without --logs, no log table should appear."""
        egg_path = pack_with_raw(sample_egg, tmp_path / "test.egg", {})
        result = runner.invoke(app, ["inspect", str(egg_path)])
        assert result.exit_code == 0
        assert "Spawn Log" not in result.output
        assert "No pipeline logs" not in result.output

    def test_logs_flag_empty_logs(self, sample_egg: Egg, tmp_path: Path):
        """--logs with empty spawn_log shows 'No pipeline logs'."""
        egg_path = pack_with_raw(sample_egg, tmp_path / "test.egg", {})
        result = runner.invoke(app, ["inspect", str(egg_path), "--logs"])
        assert result.exit_code == 0
        assert "No pipeline logs" in result.output

    def test_logs_flag_with_redactions(self, sample_egg: Egg, tmp_path: Path):
        spawn_log = [
            {"type": "redaction", "source": "memory:m1", "pii_type": "EMAIL_ADDRESS"},
            {"type": "redaction", "source": "memory:m1", "pii_type": "PERSON"},
            {"type": "redaction", "source": "raw:soul.md", "pii_type": "EMAIL_ADDRESS"},
        ]
        egg_path = pack_with_raw(
            sample_egg, tmp_path / "test.egg", {}, spawn_log=spawn_log
        )
        result = runner.invoke(app, ["inspect", str(egg_path), "--logs"])
        assert result.exit_code == 0
        assert "Spawn Log" in result.output
        assert "redaction" in result.output
        assert "3" in result.output  # count

    def test_logs_flag_with_classifications(self, sample_egg: Egg, tmp_path: Path):
        spawn_log = [
            {"type": "classification", "record_id": "m1", "assigned_label": "skill", "confidence": 0.92},
            {"type": "classification", "record_id": "m2", "assigned_label": "memory", "confidence": 0.85},
        ]
        egg_path = pack_with_raw(
            sample_egg, tmp_path / "test.egg", {}, spawn_log=spawn_log
        )
        result = runner.invoke(app, ["inspect", str(egg_path), "--logs"])
        assert result.exit_code == 0
        assert "classification" in result.output
        assert "skill" in result.output
        assert "memory" in result.output

    def test_logs_flag_with_extractions(self, sample_egg: Egg, tmp_path: Path):
        spawn_log = [
            {"type": "extraction", "record_id": "m1", "values": [], "types": ["date", "money"], "count": 2},
        ]
        egg_path = pack_with_raw(
            sample_egg, tmp_path / "test.egg", {}, spawn_log=spawn_log
        )
        result = runner.invoke(app, ["inspect", str(egg_path), "--logs"])
        assert result.exit_code == 0
        assert "extraction" in result.output
        assert "date" in result.output
        assert "money" in result.output

    def test_logs_flag_mixed_types(self, sample_egg: Egg, tmp_path: Path):
        """Multiple log types are grouped separately."""
        spawn_log = [
            {"type": "redaction", "source": "memory:m1", "pii_type": "EMAIL_ADDRESS"},
            {"type": "classification", "record_id": "m2", "assigned_label": "skill", "confidence": 0.9},
            {"type": "extraction", "record_id": "m3", "values": [], "types": ["url"], "count": 1},
        ]
        egg_path = pack_with_raw(
            sample_egg, tmp_path / "test.egg", {}, spawn_log=spawn_log
        )
        result = runner.invoke(app, ["inspect", str(egg_path), "--logs"])
        assert result.exit_code == 0
        assert "redaction" in result.output
        assert "classification" in result.output
        assert "extraction" in result.output

    def test_logs_flag_with_llm_calls(self, sample_egg: Egg, tmp_path: Path):
        """LLM call entries show provider and latency."""
        spawn_log = [
            {"type": "llm_call", "provider": "anthropic", "model": "claude-3", "latency_ms": 320},
            {"type": "llm_call", "provider": "anthropic", "model": "claude-3", "latency_ms": 180},
        ]
        egg_path = pack_with_raw(
            sample_egg, tmp_path / "test.egg", {}, spawn_log=spawn_log
        )
        result = runner.invoke(app, ["inspect", str(egg_path), "--logs"])
        assert result.exit_code == 0
        assert "llm_call" in result.output
        assert "anthropic" in result.output
        assert "500ms" in result.output  # 320 + 180

    def test_basic_inspect_still_works(self, sample_egg: Egg, tmp_path: Path):
        """Ensure the base inspect output is unaffected by new flag."""
        egg_path = pack_with_raw(sample_egg, tmp_path / "test.egg", {})
        result = runner.invoke(app, ["inspect", str(egg_path)])
        assert result.exit_code == 0
        assert "nydus 0.1.0" in result.output
        assert "openclaw" in result.output
