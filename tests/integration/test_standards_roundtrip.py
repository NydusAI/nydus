"""Integration tests for agentic standards round-trip.

Covers:
  25. spawn → inspect → extract round-trip
  26. source with apm.yml → spawn passthrough → extract
  27. A2A generation with and without LLM

Marked ``@pytest.mark.integration``: requires ``gitleaks`` on PATH.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pynydus.cmd.main import app
from pynydus.common.enums import AgentType
from pynydus.engine.hatcher import hatch
from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective
from pynydus.engine.packager import load, save
from pynydus.engine.pipeline import spawn
from pynydus.standards import a2a as a2a_mod
from typer.testing import CliRunner

pytestmark = pytest.mark.integration
runner = CliRunner()


# =====================================================================
# Helpers
# =====================================================================


def _openclaw_source(d: Path, *, apm: bool = False) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "SOUL.md").write_text("I am a helpful travel assistant.\n")
    (d / "MEMORY.md").write_text("User prefers window seats.\n")
    skills = d / "skills"
    skills.mkdir()
    (skills / "search.md").write_text("Search for flights and hotels.\n")
    if apm:
        (d / "apm.yml").write_text("name: travel-bot\nversion: 1.0.0\nruntime: python\n")
    return d


# =====================================================================
# 25. spawn → inspect → extract round-trip
# =====================================================================


class TestSpawnInspectExtractRoundtrip:
    def test_full_roundtrip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        src = _openclaw_source(tmp_path / "src")
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {src}\n")
        monkeypatch.chdir(tmp_path)

        egg_path = tmp_path / "agent.egg"

        # spawn via CLI
        result = runner.invoke(app, ["spawn", "-o", str(egg_path)], catch_exceptions=False)
        assert result.exit_code == 0, result.output
        assert egg_path.exists()

        # inspect via CLI
        result = runner.invoke(app, ["inspect", str(egg_path)])
        assert result.exit_code == 0
        assert "validation:" in result.output
        assert "a2a=present" in result.output
        assert "agents.md=present" in result.output
        assert "specs=" in result.output

        # extract all via CLI
        out = tmp_path / "extracted"
        result = runner.invoke(app, ["extract", "all", "--from", str(egg_path), "-o", str(out)])
        assert result.exit_code == 0
        assert "Extracted" in result.output

        # verify extracted artifacts
        assert (out / "agent-card.json").exists()
        card = json.loads((out / "agent-card.json").read_text())
        assert "skills" in card

        assert (out / "AGENTS.md").exists()
        agents_md = (out / "AGENTS.md").read_text()
        assert "## Prerequisites" in agents_md
        assert "## Hatch" in agents_md

        assert (out / "specs" / "manifest.json").exists()
        manifest = json.loads((out / "specs" / "manifest.json").read_text())
        assert "nydus_version" in manifest
        assert "specs" in manifest

    def test_extract_individual_standards(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        src = _openclaw_source(tmp_path / "src")
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {src}\n")
        monkeypatch.chdir(tmp_path)
        egg_path = tmp_path / "agent.egg"

        result = runner.invoke(app, ["spawn", "-o", str(egg_path)], catch_exceptions=False)
        assert result.exit_code == 0

        # extract a2a
        a2a_out = tmp_path / "a2a"
        result = runner.invoke(app, ["extract", "a2a", "--from", str(egg_path), "-o", str(a2a_out)])
        assert result.exit_code == 0
        assert (a2a_out / "agent-card.json").exists()

        # extract agents
        agents_out = tmp_path / "agents"
        result = runner.invoke(
            app, ["extract", "agents", "--from", str(egg_path), "-o", str(agents_out)]
        )
        assert result.exit_code == 0
        assert (agents_out / "AGENTS.md").exists()

        # extract specs
        specs_out = tmp_path / "specs"
        result = runner.invoke(
            app, ["extract", "specs", "--from", str(egg_path), "-o", str(specs_out)]
        )
        assert result.exit_code == 0
        assert (specs_out / "manifest.json").exists()
        assert (specs_out / "mcp.md").exists()


# =====================================================================
# 26. source with apm.yml → spawn passthrough → extract
# =====================================================================


class TestApmPassthrough:
    def test_apm_yml_roundtrip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        src = _openclaw_source(tmp_path / "src", apm=True)
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {src}\n")
        monkeypatch.chdir(tmp_path)

        egg_path = tmp_path / "agent.egg"
        result = runner.invoke(app, ["spawn", "-o", str(egg_path)], catch_exceptions=False)
        assert result.exit_code == 0

        # inspect should show apm=present
        result = runner.invoke(app, ["inspect", str(egg_path)])
        assert "apm=present" in result.output

        # extract apm
        apm_out = tmp_path / "apm_ext"
        result = runner.invoke(app, ["extract", "apm", "--from", str(egg_path), "-o", str(apm_out)])
        assert result.exit_code == 0
        assert "Extracted" in result.output

        apm_path = apm_out / "apm.yml"
        assert apm_path.exists()
        content = apm_path.read_text()
        assert "travel-bot" in content
        assert "1.0.0" in content

    def test_apm_preserved_through_save_load(self, tmp_path: Path):
        src = _openclaw_source(tmp_path / "src", apm=True)
        config = NydusfileConfig(
            sources=[SourceDirective(agent_type="openclaw", path=str(src))],
            redact=True,
        )
        egg, raw_artifacts, logs = spawn(config, nydusfile_dir=tmp_path)
        assert egg.apm_yml is not None
        assert "travel-bot" in egg.apm_yml

        egg_path = tmp_path / "test.egg"
        save(egg, egg_path, raw_artifacts=raw_artifacts, spawn_log=logs.get("spawn_log"))

        loaded = load(egg_path)
        assert loaded.apm_yml is not None
        assert loaded.apm_yml == egg.apm_yml

    def test_apm_absent_when_no_source_apm(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        src = _openclaw_source(tmp_path / "src", apm=False)
        nydusfile = tmp_path / "Nydusfile"
        nydusfile.write_text(f"SOURCE openclaw {src}\n")
        monkeypatch.chdir(tmp_path)

        egg_path = tmp_path / "agent.egg"
        result = runner.invoke(app, ["spawn", "-o", str(egg_path)], catch_exceptions=False)
        assert result.exit_code == 0

        # extract apm should report not present
        apm_out = tmp_path / "no_apm"
        result = runner.invoke(app, ["extract", "apm", "--from", str(egg_path), "-o", str(apm_out)])
        assert result.exit_code == 0
        assert "No apm.yml" in result.output

    def test_apm_written_at_hatch(self, tmp_path: Path):
        src = _openclaw_source(tmp_path / "src", apm=True)
        config = NydusfileConfig(
            sources=[SourceDirective(agent_type="openclaw", path=str(src))],
            redact=True,
        )
        egg, raw_artifacts, logs = spawn(config, nydusfile_dir=tmp_path)

        egg_path = tmp_path / "test.egg"
        save(egg, egg_path, raw_artifacts=raw_artifacts, spawn_log=logs.get("spawn_log"))
        loaded = load(egg_path, include_raw=True)

        out_dir = tmp_path / "hatched"
        hatch(
            loaded,
            target=AgentType.OPENCLAW,
            output_dir=out_dir,
            raw_artifacts=loaded.raw_artifacts or raw_artifacts,
        )
        assert (out_dir / "apm.yml").exists()
        assert "travel-bot" in (out_dir / "apm.yml").read_text()


# =====================================================================
# 27. A2A generation with and without LLM
# =====================================================================


class TestA2AGeneration:
    def test_deterministic_generation_from_spawn(self, tmp_path: Path):
        src = _openclaw_source(tmp_path / "src")
        config = NydusfileConfig(
            sources=[SourceDirective(agent_type="openclaw", path=str(src))],
            redact=True,
        )
        egg, _, _ = spawn(config, nydusfile_dir=tmp_path)

        assert egg.a2a_card is not None
        assert "skills" in egg.a2a_card
        assert isinstance(egg.a2a_card["skills"], list)
        assert len(egg.a2a_card["skills"]) >= 1
        assert egg.a2a_card["skills"][0]["name"] == "search"

    def test_a2a_passthrough_when_source_has_card(self, tmp_path: Path):
        src = _openclaw_source(tmp_path / "src")
        card = {
            "name": "Custom Agent",
            "description": "User-authored agent card.",
            "version": "2.0",
            "skills": [{"id": "s1", "name": "custom-skill", "description": "Custom."}],
            "supportedInterfaces": [],
            "capabilities": {"streaming": True},
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
        }
        (src / "agent-card.json").write_text(json.dumps(card))

        config = NydusfileConfig(
            sources=[SourceDirective(agent_type="openclaw", path=str(src))],
            redact=True,
        )
        egg, _, _ = spawn(config, nydusfile_dir=tmp_path)

        assert egg.a2a_card is not None
        assert egg.a2a_card["name"] == "Custom Agent"
        assert egg.a2a_card["skills"][0]["name"] == "custom-skill"

    def test_a2a_generation_with_mock_llm(self):
        from pynydus.api.schemas import AgentSkill

        from conftest import make_egg

        egg = make_egg(
            agent_name="SupportBot",
            agent_description="Handles customer support.",
            skills=[
                AgentSkill(
                    name="ticket-create",
                    description="Create support ticket.",
                    body="Create a ticket.",
                    metadata={"id": "s1"},
                ),
            ],
        )

        def llm_fn(card):
            card["description"] = "LLM-polished: " + card["description"]
            return card

        result = a2a_mod.generate(egg, llm_fn=llm_fn)
        doc = json.loads(result["agent-card.json"])
        assert doc["description"].startswith("LLM-polished:")
        assert doc["name"] == "SupportBot"

    def test_generated_card_validates_against_schema(self, tmp_path: Path):
        src = _openclaw_source(tmp_path / "src")
        config = NydusfileConfig(
            sources=[SourceDirective(agent_type="openclaw", path=str(src))],
            redact=True,
        )
        egg, _, _ = spawn(config, nydusfile_dir=tmp_path)

        issues = a2a_mod.validate(egg)
        assert all(i.level != "error" for i in issues)

    def test_a2a_card_preserved_through_save_load(self, tmp_path: Path):
        src = _openclaw_source(tmp_path / "src")
        config = NydusfileConfig(
            sources=[SourceDirective(agent_type="openclaw", path=str(src))],
            redact=True,
        )
        egg, raw, logs = spawn(config, nydusfile_dir=tmp_path)

        egg_path = tmp_path / "test.egg"
        save(egg, egg_path, raw_artifacts=raw, spawn_log=logs.get("spawn_log"))

        loaded = load(egg_path)
        assert loaded.a2a_card is not None
        assert loaded.a2a_card == egg.a2a_card
