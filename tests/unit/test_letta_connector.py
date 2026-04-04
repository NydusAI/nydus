"""Contract tests for Letta spawner and hatcher."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from pynydus.agents.letta.hatcher import LettaHatcher
from pynydus.agents.letta.spawner import LettaSpawner
from pynydus.api.schemas import MemoryRecord, SkillRecord
from pynydus.common.enums import AgentType, MemoryLabel

from conftest import make_egg


@pytest.fixture
def spawner():
    return LettaSpawner()


@pytest.fixture
def hatcher():
    return LettaHatcher()


@pytest.fixture
def letta_files():
    agent_state = {
        "name": "research_bot",
        "system": "You are a research assistant. Be thorough.",
        "memory": {
            "persona": {"value": "I specialize in machine learning research."},
            "human": {"value": "The user is a PhD student studying CV."},
        },
        "tools": [
            {
                "name": "search_papers",
                "source_code": "def search_papers(q: str) -> str:\n    return q\n",
            }
        ],
    }
    archival = [
        {"text": "GPT-4 released March 2023.", "timestamp": "2024-01-15T10:00:00Z"},
        {"text": "ViT uses patch embeddings.", "timestamp": "2024-02-01T12:00:00Z"},
    ]
    return {
        "agent_state.json": json.dumps(agent_state, indent=2),
        "archival_memory.json": json.dumps(archival, indent=2),
        "tools/analyze.py": (
            'def analyze(data: str) -> str:\n    """Analyze data."""\n    return data\n'
        ),
    }


def _rich_egg():
    return make_egg(
        agent_type=AgentType.LETTA,
        skills=[
            SkillRecord(id="s1", name="greet", agent_type="letta", content="def greet(): pass")
        ],
        memory=[
            MemoryRecord(
                id="m1",
                text="I study ML.",
                label=MemoryLabel.PERSONA,
                agent_type="letta",
                source_store="agent_state.json",
            ),
            MemoryRecord(
                id="m2",
                text="Be helpful.",
                label=MemoryLabel.FLOW,
                agent_type="letta",
                source_store="system_prompt.md",
            ),
            MemoryRecord(
                id="m3",
                text="PhD student.",
                label=MemoryLabel.CONTEXT,
                agent_type="letta",
                source_store="agent_state.json",
            ),
            MemoryRecord(
                id="m4",
                text="GPT-4 released 2023.",
                label=MemoryLabel.STATE,
                agent_type="letta",
                source_store="archival",
            ),
        ],
    )


class TestLettaParse:
    def test_persona(self, spawner, letta_files):
        result = spawner.parse(letta_files)
        persona = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert any("machine learning" in m.text for m in persona)

    def test_human_context(self, spawner, letta_files):
        result = spawner.parse(letta_files)
        ctx = [m for m in result.memory if m.label == MemoryLabel.CONTEXT]
        assert any("PhD student" in m.text for m in ctx)

    def test_system_flow(self, spawner, letta_files):
        result = spawner.parse(letta_files)
        flow = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert any("research assistant" in m.text for m in flow)

    def test_archival_state(self, spawner, letta_files):
        result = spawner.parse(letta_files)
        state = [m for m in result.memory if m.label == MemoryLabel.STATE]
        assert len(state) >= 2
        assert any(m.timestamp is not None for m in state)

    def test_tools_dir(self, spawner, letta_files):
        result = spawner.parse(letta_files)
        assert any(s.source_file == "tools/analyze.py" for s in result.skills)

    def test_tools_from_state(self, spawner, letta_files):
        result = spawner.parse(letta_files)
        assert any("search papers" in s.name for s in result.skills)

    def test_system_prompt_fallback(self, spawner):
        files = {"system_prompt.md": "You are a coding assistant."}
        result = spawner.parse(files)
        flow = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert any("coding assistant" in m.text for m in flow)

    def test_optional_files(self, spawner):
        files = {"agent_state.json": json.dumps({"name": "bot", "memory": {}, "tools": []})}
        result = spawner.parse(files)
        assert isinstance(result.skills, list)

    def test_agent_file(self, spawner):
        af = {
            "memory": {"persona": "I am a helper.", "human": "User likes code."},
            "system": "Be helpful.",
            "tools": [{"name": "greet", "source_code": "def greet(): pass"}],
            "tool_rules": [{"type": "sequence", "tools": ["greet"]}],
        }
        files = {"agent.af": json.dumps(af)}
        result = spawner.parse(files)
        assert len(result.skills) >= 1

    def test_malformed_agent_state(self, spawner):
        files = {"agent_state.json": "NOT VALID JSON"}
        result = spawner.parse(files)
        assert isinstance(result.skills, list)
        assert isinstance(result.memory, list)

    def test_agent_state_non_dict(self, spawner):
        files = {"agent_state.json": '"just a string"'}
        result = spawner.parse(files)
        assert isinstance(result.skills, list)

    def test_archival_bad_json(self, spawner):
        files = {"archival_memory.json": "<<<BROKEN>>>"}
        result = spawner.parse(files)
        state = [m for m in result.memory if m.label == MemoryLabel.STATE]
        assert len(state) == 0

    def test_af_bad_json(self, spawner):
        files = {"agent.af": "NOT JSON", "system_prompt.md": "You are helpful."}
        result = spawner.parse(files)
        flow = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert any("helpful" in m.text for m in flow)

    def test_tool_entries_not_dicts(self, spawner):
        state = {
            "name": "bot",
            "memory": {},
            "tools": ["string_tool", 42, {"name": "real", "source_code": "def f(): pass"}],
        }
        files = {"agent_state.json": json.dumps(state)}
        result = spawner.parse(files)
        assert len(result.skills) == 1
        assert result.skills[0].source_file == "agent_state.json"


class TestLettaParseDB:
    def test_sqlite(self, spawner, tmp_path: Path):
        db_path = tmp_path / "agent.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE blocks (label TEXT, value TEXT)")
        conn.execute("INSERT INTO blocks VALUES ('persona', 'I am helpful.')")
        conn.execute("INSERT INTO blocks VALUES ('human', 'User likes code.')")
        conn.execute("CREATE TABLE archival_memory (text TEXT)")
        conn.execute("INSERT INTO archival_memory VALUES ('A stored fact.')")
        conn.execute("CREATE TABLE tools (name TEXT, source_code TEXT)")
        conn.execute("INSERT INTO tools VALUES ('calc', 'def calc(): pass')")
        conn.commit()
        conn.close()
        result = spawner.parse_db(db_path)
        assert len(result.memory) >= 3
        assert len(result.skills) >= 1


class TestLettaDetect:
    def test_marker_dir(self, tmp_path: Path, spawner):
        (tmp_path / ".letta").mkdir()
        assert spawner.detect(tmp_path) is True


class TestLettaRender:
    def test_agent_state(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        state = json.loads(result.files["agent_state.json"])
        assert "memory" in state
        assert "tools" in state

    def test_archival(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        entries = json.loads(result.files["archival_memory.json"])
        assert len(entries) >= 1

    def test_system_prompt(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        assert "system_prompt.md" in result.files

    def test_tools(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        assert any(f.startswith("tools/") for f in result.files)

    def test_credentials(self, hatcher):
        from pynydus.api.schemas import SecretRecord, SecretsModule
        from pynydus.common.enums import Bucket, InjectionMode, SecretKind

        egg = _rich_egg()
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
        egg.manifest.included_modules = [Bucket.SKILL, Bucket.MEMORY, Bucket.SECRET]
        result = hatcher.render(egg)
        assert "{{SECRET_001}}" in result.files[".letta/config.json"]

    def test_empty_egg(self, hatcher):
        egg = make_egg(skills=[], memory=[])
        result = hatcher.render(egg)
        state = json.loads(result.files["agent_state.json"])
        assert state["tools"] == []
        assert state["memory"] == {}
