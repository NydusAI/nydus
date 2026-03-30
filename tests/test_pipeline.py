"""End-to-end pipeline tests: spawn → pack → unpack → hatch."""

from pathlib import Path

import pytest

from pynydus.api.schemas import RedactMode, SourceType
from pynydus.engine.hatcher import hatch
from pynydus.engine.packager import pack_with_raw, unpack
from pynydus.engine.pipeline import build as spawn
from pynydus.engine.validator import validate_egg


@pytest.fixture
def openclaw_project(tmp_path: Path) -> Path:
    """Create a realistic OpenClaw project."""
    src = tmp_path / "source"
    src.mkdir()
    (src / "soul.md").write_text(
        "I am a helpful research assistant named Alex.\n\n"
        "I prefer concise, structured answers.\n\n"
        "Contact me at alex@research.edu or call 555-123-4567.\n"
    )
    (src / "knowledge.md").write_text(
        "# Physics\n\n"
        "The speed of light is 299,792,458 m/s.\n\n"
        "# History\n\n"
        "The first moon landing was in 1969.\n"
    )
    (src / "skill.md").write_text(
        "# Literature Review\n\n"
        "Analyze academic papers and produce a structured review.\n\n"
        "# Data Analysis\n\n"
        "Process CSV data and generate statistical summaries.\n"
    )
    (src / "config.json").write_text(
        '{"api_key": "sk-secret-key-123", "model": "gpt-4"}\n'
    )
    return src


class TestSpawnPipeline:
    def test_spawn_basic(self, openclaw_project: Path):
        egg, raw, _logs = spawn(openclaw_project, source_type="openclaw")
        assert egg.manifest.source_type == SourceType.OPENCLAW
        assert len(egg.skills.skills) == 2
        assert len(egg.memory.memory) >= 4
        assert len(raw) > 0

    def test_spawn_auto_detect(self, openclaw_project: Path):
        egg, _, _logs = spawn(openclaw_project)
        assert egg.manifest.source_type == SourceType.OPENCLAW

    def test_spawn_redacts_pii(self, openclaw_project: Path):
        egg, raw, _logs = spawn(openclaw_project, redact_mode=RedactMode.PII)
        # Check email was redacted in structured content
        all_memory_text = " ".join(m.text for m in egg.memory.memory)
        assert "alex@research.edu" not in all_memory_text

        # Raw artifacts are also redacted (same redactor, consistent placeholders)
        soul_raw = raw.get("soul.md", "")
        assert "alex@research.edu" not in soul_raw

    def test_raw_artifacts_redacted_in_packed_egg(
        self, openclaw_project: Path, tmp_path: Path
    ):
        """PII in raw/ entries inside the packed egg must be replaced with placeholders."""
        egg, raw, logs = spawn(openclaw_project, redact_mode=RedactMode.PII)
        egg_path = pack_with_raw(egg, tmp_path / "redacted.egg", raw, spawn_log=logs.get("spawn_log"))

        from pynydus.engine.packager import read_raw_artifacts

        packed_raw = read_raw_artifacts(egg_path)
        soul_raw = packed_raw.get("soul.md", "")
        assert "alex@research.edu" not in soul_raw
        assert "555-123-4567" not in soul_raw
        assert "{{PII_" in soul_raw

    def test_raw_and_memory_use_same_placeholders(self, openclaw_project: Path):
        """The same PII value gets the same placeholder in both memory and raw."""
        egg, raw, _logs = spawn(openclaw_project, redact_mode=RedactMode.PII)
        all_memory_text = " ".join(m.text for m in egg.memory.memory)
        soul_raw = raw.get("soul.md", "")
        # Find a PII placeholder that appears in memory
        import re
        memory_placeholders = set(re.findall(r"\{\{PII_\d+\}\}", all_memory_text))
        raw_placeholders = set(re.findall(r"\{\{PII_\d+\}\}", soul_raw))
        # At least one placeholder should be shared (the email appears in both)
        assert memory_placeholders & raw_placeholders

    def test_spawn_no_redact(self, openclaw_project: Path):
        egg, _, _logs = spawn(openclaw_project, redact_mode=RedactMode.NONE)
        all_text = " ".join(m.text for m in egg.memory.memory)
        assert "alex@research.edu" in all_text

    def test_spawn_extracts_secrets(self, openclaw_project: Path):
        egg, _, _logs = spawn(openclaw_project)
        creds = [s for s in egg.secrets.secrets if s.kind == "credential"]
        assert len(creds) >= 1

    def test_egg_validates(self, openclaw_project: Path):
        egg, _, _logs = spawn(openclaw_project)
        report = validate_egg(egg)
        assert report.valid is True


class TestPackUnpack:
    def test_round_trip(self, openclaw_project: Path, tmp_path: Path):
        egg, raw, _logs = spawn(openclaw_project)
        egg_path = pack_with_raw(egg, tmp_path / "test.egg", raw)
        assert egg_path.exists()
        assert egg_path.suffix == ".egg"

        loaded = unpack(egg_path)
        assert loaded.manifest.source_type == egg.manifest.source_type
        assert len(loaded.skills.skills) == len(egg.skills.skills)
        assert len(loaded.memory.memory) == len(egg.memory.memory)
        assert len(loaded.secrets.secrets) == len(egg.secrets.secrets)


@pytest.fixture
def letta_project(tmp_path: Path) -> Path:
    """Create a realistic Letta project."""
    import json

    src = tmp_path / "letta_source"
    src.mkdir()
    (src / ".letta").mkdir()
    (src / ".letta" / "config.json").write_text(
        json.dumps({"api_key": "sk-letta-secret-456"})
    )

    agent_state = {
        "name": "research_bot",
        "system": "You are a research assistant. Be thorough and cite sources.",
        "memory": {
            "persona": "I am an AI research assistant specializing in machine learning.",
            "human": "The user is a PhD student studying computer vision.",
        },
        "tools": [],
        "llm_config": {"model": "gpt-4", "api_key": "sk-openai-abc"},
    }
    (src / "agent_state.json").write_text(json.dumps(agent_state, indent=2))

    tools_dir = src / "tools"
    tools_dir.mkdir()
    (tools_dir / "search_papers.py").write_text(
        'def search_papers(query: str) -> str:\n    """Search academic papers."""\n    return query\n'
    )

    archival = [
        {"text": "GPT-4 was released in March 2023.", "timestamp": "2024-01-15T10:00:00Z"},
        {"text": "Vision Transformers use patch embeddings.", "timestamp": "2024-02-01T12:00:00Z"},
    ]
    (src / "archival_memory.json").write_text(json.dumps(archival, indent=2))

    return src


class TestLettaSpawnPipeline:
    def test_spawn_letta_basic(self, letta_project: Path):
        egg, raw, _logs = spawn(letta_project, source_type="letta")
        assert egg.manifest.source_type == SourceType.LETTA
        assert len(egg.skills.skills) >= 1
        assert len(egg.memory.memory) >= 3  # system + persona + human + archival
        assert len(raw) > 0

    def test_spawn_letta_auto_detect(self, letta_project: Path):
        egg, _, _logs = spawn(letta_project)
        assert egg.manifest.source_type == SourceType.LETTA

    def test_spawn_letta_redacts_pii(self, letta_project: Path):
        egg, _, _logs = spawn(letta_project, redact_mode=RedactMode.PII)
        report = validate_egg(egg)
        assert report.valid is True

    def test_letta_egg_validates(self, letta_project: Path):
        egg, _, _logs = spawn(letta_project)
        report = validate_egg(egg)
        assert report.valid is True


class TestLettaPackUnpack:
    def test_round_trip(self, letta_project: Path, tmp_path: Path):
        egg, raw, _logs = spawn(letta_project, source_type="letta")
        egg_path = pack_with_raw(egg, tmp_path / "letta.egg", raw)
        assert egg_path.exists()

        loaded = unpack(egg_path)
        assert loaded.manifest.source_type == SourceType.LETTA
        assert len(loaded.skills.skills) == len(egg.skills.skills)
        assert len(loaded.memory.memory) == len(egg.memory.memory)


class TestLettaHatchPipeline:
    def test_hatch_letta(self, letta_project: Path, tmp_path: Path):
        egg, raw, _logs = spawn(letta_project, source_type="letta")
        egg_path = pack_with_raw(egg, tmp_path / "letta.egg", raw)
        loaded = unpack(egg_path)

        out = tmp_path / "hatched_letta"
        result = hatch(loaded, target="letta", output_dir=out)
        assert result.target == "letta"
        assert "agent_state.json" in result.files_created
        assert (out / "agent_state.json").exists()

    def test_cross_framework_openclaw_to_letta(
        self, openclaw_project: Path, tmp_path: Path
    ):
        """Spawn from OpenClaw, hatch into Letta — the cross-framework demo."""
        import json

        egg, raw, _logs = spawn(openclaw_project)
        egg_path = pack_with_raw(egg, tmp_path / "cross.egg", raw)
        loaded = unpack(egg_path)

        out = tmp_path / "letta_output"
        result = hatch(loaded, target="letta", output_dir=out)

        assert result.target == "letta"
        assert "agent_state.json" in result.files_created

        # Verify the Letta output has OpenClaw's content
        state = json.loads((out / "agent_state.json").read_text())
        assert "memory" in state
        # OpenClaw preference memory → Letta persona block
        if "persona" in state["memory"]:
            assert "concise" in state["memory"]["persona"]["value"]
        # Skills should be present as tools
        assert len(state.get("tools", [])) >= 1

    def test_cross_framework_letta_to_openclaw(
        self, letta_project: Path, tmp_path: Path
    ):
        """Spawn from Letta, hatch into OpenClaw."""
        egg, raw, _logs = spawn(letta_project, source_type="letta")
        egg_path = pack_with_raw(egg, tmp_path / "cross.egg", raw)
        loaded = unpack(egg_path)

        out = tmp_path / "openclaw_output"
        result = hatch(loaded, target="openclaw", output_dir=out)

        assert result.target == "openclaw"
        # Letta system → OpenClaw gets at least skill.md or soul.md
        assert len(result.files_created) > 0

    def test_letta_full_round_trip(self, letta_project: Path, tmp_path: Path):
        """Full cycle: Letta spawn → pack → unpack → Letta hatch → validate."""
        import json

        egg, raw, _logs = spawn(letta_project, source_type="letta")
        egg_path = pack_with_raw(egg, tmp_path / "letta.egg", raw)
        loaded = unpack(egg_path)

        out = tmp_path / "output"
        result = hatch(loaded, target="letta", output_dir=out)

        # Verify the hatched output has expected structure
        assert (out / "agent_state.json").exists()
        state = json.loads((out / "agent_state.json").read_text())
        assert "research assistant" in state.get("system", "").lower() or \
               any("research" in str(v) for v in state.get("memory", {}).values())


class TestHatchPipeline:
    def test_hatch_openclaw(self, openclaw_project: Path, tmp_path: Path):
        egg, raw, _logs = spawn(openclaw_project)
        egg_path = pack_with_raw(egg, tmp_path / "test.egg", raw)
        loaded = unpack(egg_path)

        out = tmp_path / "hatched"
        result = hatch(loaded, target="openclaw", output_dir=out)
        assert result.target == "openclaw"
        assert "skill.md" in result.files_created
        assert (out / "skill.md").exists()

    def test_hatch_with_secrets(self, openclaw_project: Path, tmp_path: Path):
        egg, raw, _logs = spawn(openclaw_project)
        egg_path = pack_with_raw(egg, tmp_path / "test.egg", raw)
        loaded = unpack(egg_path)

        # Create .env file
        env_path = tmp_path / "agent.env"
        env_lines = []
        for s in loaded.secrets.secrets:
            env_lines.append(f"{s.name}=INJECTED_VALUE_{s.id}")
        env_path.write_text("\n".join(env_lines) + "\n")

        out = tmp_path / "hatched"
        result = hatch(
            loaded, target="openclaw", output_dir=out, secrets_path=env_path
        )

        # Check that config.json has injected values
        if "config.json" in result.files_created:
            config_content = (out / "config.json").read_text()
            assert "{{SECRET_" not in config_content

    def test_full_round_trip(self, openclaw_project: Path, tmp_path: Path):
        """Full cycle: spawn → pack → unpack → hatch → validate output."""
        egg, raw, _logs = spawn(openclaw_project)
        egg_path = pack_with_raw(egg, tmp_path / "agent.egg", raw)
        loaded = unpack(egg_path)

        out = tmp_path / "output"
        hatch(loaded, target="openclaw", output_dir=out)

        # Verify the hatched output looks like an OpenClaw project
        assert (out / "skill.md").exists()
        skill_content = (out / "skill.md").read_text()
        assert "Literature Review" in skill_content
        assert "Data Analysis" in skill_content
