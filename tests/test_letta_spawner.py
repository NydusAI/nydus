"""Tests for the Letta spawner connector."""

import json
import sqlite3
from pathlib import Path

import pytest

from pynydus.api.errors import ConnectorError
from pynydus.api.schemas import MemoryLabel
from pynydus.agents.letta.spawner import LettaSpawner


@pytest.fixture
def letta_files() -> dict[str, str]:
    """Minimal Letta file dict for parse() testing."""
    agent_state = {
        "name": "research_assistant",
        "system": "You are a helpful research assistant. Be concise and accurate.",
        "memory": {
            "persona": "I am a research assistant specializing in AI papers.",
            "human": {
                "value": "The user is a graduate student working on NLP.",
                "limit": 5000,
            },
        },
        "tools": [
            {
                "name": "search_arxiv",
                "source_code": (
                    'def search_arxiv(query: str) -> str:\n'
                    '    """Search arXiv papers."""\n'
                    '    return f"Results for {query}"'
                ),
            }
        ],
        "llm_config": {
            "model": "gpt-4",
            "api_key": "sk-openai-xyz789",
        },
    }
    archival = [
        {"text": "The transformer architecture was introduced in 2017.", "timestamp": "2024-01-15T10:30:00Z"},
        {"text": "BERT uses bidirectional attention.", "timestamp": "2024-01-16T14:00:00Z"},
    ]
    return {
        "agent_state.json": json.dumps(agent_state, indent=2),
        "archival_memory.json": json.dumps(archival, indent=2),
        "tools/web_search.py": 'def web_search(query: str) -> str:\n    """Search the web."""\n    return query\n',
        "tools/calculator.py": 'def calculate(expr: str) -> float:\n    """Evaluate a math expression."""\n    return eval(expr)\n',
        ".letta/config.json": json.dumps({"api_key": "sk-letta-abc123", "base_url": "http://localhost:8283"}),
    }


@pytest.fixture
def letta_project(tmp_path: Path, letta_files: dict[str, str]) -> Path:
    """Create a minimal Letta project directory on disk."""
    (tmp_path / ".letta").mkdir()
    for rel_path, content in letta_files.items():
        fpath = tmp_path / rel_path
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content)
    return tmp_path


@pytest.fixture
def letta_db_project(tmp_path: Path) -> Path:
    """Create a Letta project with a SQLite database."""
    db_path = tmp_path / "agent.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE agents (id TEXT, name TEXT, llm_config TEXT, metadata TEXT)"
    )
    conn.execute(
        "INSERT INTO agents VALUES (?, ?, ?, ?)",
        (
            "agent-001",
            "db_agent",
            json.dumps({"model": "gpt-4", "api_key": "sk-db-secret"}),
            json.dumps({"owner": "test"}),
        ),
    )
    conn.execute("CREATE TABLE blocks (label TEXT, value TEXT)")
    conn.execute("INSERT INTO blocks VALUES (?, ?)", ("persona", "I am a coding assistant."))
    conn.execute("INSERT INTO blocks VALUES (?, ?)", ("human", "The user likes Python."))
    conn.execute("CREATE TABLE archival_memory (text TEXT, created_at TEXT)")
    conn.execute(
        "INSERT INTO archival_memory VALUES (?, ?)",
        ("Python was created by Guido van Rossum.", "2024-03-01T12:00:00Z"),
    )
    conn.execute("CREATE TABLE tools (name TEXT, source_code TEXT)")
    conn.execute(
        "INSERT INTO tools VALUES (?, ?)",
        ("lint_code", "def lint_code(code: str) -> str:\n    return code"),
    )
    conn.commit()
    conn.close()
    return tmp_path


@pytest.fixture
def spawner() -> LettaSpawner:
    return LettaSpawner()


class TestDetect:
    def test_detects_with_letta_marker(self, spawner: LettaSpawner, tmp_path: Path):
        (tmp_path / ".letta").mkdir()
        assert spawner.detect(tmp_path) is True

    def test_detects_with_agent_state(self, spawner: LettaSpawner, tmp_path: Path):
        (tmp_path / "agent_state.json").write_text("{}")
        assert spawner.detect(tmp_path) is True

    def test_detects_with_db(self, spawner: LettaSpawner, letta_db_project: Path):
        assert spawner.detect(letta_db_project) is True

    def test_detects_db_file_directly(self, spawner: LettaSpawner, letta_db_project: Path):
        db_path = letta_db_project / "agent.db"
        assert spawner.detect(db_path) is True

    def test_detects_with_tools_dir(self, spawner: LettaSpawner, tmp_path: Path):
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "search.py").write_text("def search(): pass")
        assert spawner.detect(tmp_path) is True

    def test_rejects_empty_dir(self, spawner: LettaSpawner, tmp_path: Path):
        assert spawner.detect(tmp_path) is False

    def test_rejects_file(self, spawner: LettaSpawner, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("not a dir")
        assert spawner.detect(f) is False

    def test_rejects_non_letta_db(self, spawner: LettaSpawner, tmp_path: Path):
        db_path = tmp_path / "other.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE unrelated (x TEXT)")
        conn.commit()
        conn.close()
        assert spawner.detect(db_path) is False


class TestParse:
    def test_extracts_skills(self, spawner: LettaSpawner, letta_files: dict[str, str]):
        result = spawner.parse(letta_files)
        tool_names = {s.name for s in result.skills}
        assert "web search" in tool_names
        assert "calculator" in tool_names
        assert "search arxiv" in tool_names

    def test_extracts_memory_blocks(self, spawner: LettaSpawner, letta_files: dict[str, str]):
        result = spawner.parse(letta_files)
        labels = {m.label for m in result.memory}
        assert MemoryLabel.FLOW in labels
        assert MemoryLabel.PERSONA in labels
        assert MemoryLabel.CONTEXT in labels

    def test_extracts_system_prompt(self, spawner: LettaSpawner, letta_files: dict[str, str]):
        result = spawner.parse(letta_files)
        system = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert len(system) == 1
        assert "research assistant" in system[0].text

    def test_extracts_archival_memory(self, spawner: LettaSpawner, letta_files: dict[str, str]):
        result = spawner.parse(letta_files)
        facts = [m for m in result.memory if m.label == MemoryLabel.STATE]
        assert len(facts) == 2
        assert any("transformer" in m.text for m in facts)
        assert facts[0].timestamp is not None

    def test_system_prompt_file_fallback(self, spawner: LettaSpawner):
        files = {
            "agent_state.json": json.dumps({"name": "agent", "memory": {"persona": "I am an agent."}}),
            "system_prompt.md": "You are an expert coding assistant.",
        }
        result = spawner.parse(files)
        system = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert len(system) == 1
        assert "coding assistant" in system[0].text

    def test_archival_directory_files(self, spawner: LettaSpawner):
        files = {
            "archival/note1.txt": "First archival note.",
            "archival/note2.md": "Second archival note.",
        }
        result = spawner.parse(files)
        facts = [m for m in result.memory if m.label == MemoryLabel.STATE]
        assert len(facts) == 2

    def test_memory_block_as_dict(self, spawner: LettaSpawner):
        files = {
            "agent_state.json": json.dumps({
                "name": "agent",
                "memory": {
                    "persona": {"value": "I am a persona.", "limit": 5000},
                    "human": {"value": "User info.", "limit": 5000},
                },
            }),
        }
        result = spawner.parse(files)
        prefs = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert len(prefs) == 1
        assert "persona" in prefs[0].text


class TestParseDB:
    def test_parse_db_extracts_blocks(self, spawner: LettaSpawner, letta_db_project: Path):
        db_path = letta_db_project / "agent.db"
        result = spawner.parse_db(db_path)
        labels = {m.label for m in result.memory}
        assert MemoryLabel.PERSONA in labels
        assert MemoryLabel.CONTEXT in labels

    def test_parse_db_extracts_archival(self, spawner: LettaSpawner, letta_db_project: Path):
        db_path = letta_db_project / "agent.db"
        result = spawner.parse_db(db_path)
        facts = [m for m in result.memory if m.label == MemoryLabel.STATE]
        assert len(facts) == 1
        assert "Guido" in facts[0].text

    def test_parse_db_extracts_tools(self, spawner: LettaSpawner, letta_db_project: Path):
        db_path = letta_db_project / "agent.db"
        result = spawner.parse_db(db_path)
        assert len(result.skills) == 1
        assert result.skills[0].name == "lint code"


class TestAgentFile:
    """Tests for .af (AgentFile) format parsing."""

    def _af_data(self) -> dict:
        return {
            "system": "You are a research assistant.",
            "memory": {
                "persona": "I am a research bot.",
                "human": "The user is a student.",
            },
            "tools": [
                {
                    "name": "search_papers",
                    "source_code": "def search_papers(q: str) -> str:\n    return q",
                },
            ],
            "tool_rules": [
                {"type": "init_tool_rule", "tool_name": "search_papers"},
            ],
            "messages": [
                {"role": "user", "content": "Find papers on attention.", "created_at": "2026-01-10T08:00:00Z"},
                {"role": "assistant", "content": "Here are some results.", "created_at": "2026-01-10T08:01:00Z"},
            ],
            "env_vars": {"OPENAI_API_KEY": "sk-abc123"},
            "mcp_servers": [
                {"name": "arxiv", "url": "https://arxiv.example.com"},
            ],
            "model": "gpt-4",
            "llm_config": {"model": "gpt-4", "context_window": "128000"},
        }

    def test_detects_af_file(self, spawner: LettaSpawner, tmp_path: Path):
        af_path = tmp_path / "agent.af"
        af_path.write_text(json.dumps(self._af_data()))
        assert spawner.detect(af_path) is True

    def test_detects_af_in_directory(self, spawner: LettaSpawner, tmp_path: Path):
        af_path = tmp_path / "my_agent.af"
        af_path.write_text(json.dumps(self._af_data()))
        assert spawner.detect(tmp_path) is True

    def test_parse_af_memory_blocks(self, spawner: LettaSpawner):
        files = {"agent.af": json.dumps(self._af_data())}
        result = spawner.parse(files)
        labels = {m.label for m in result.memory}
        assert MemoryLabel.PERSONA in labels
        assert MemoryLabel.CONTEXT in labels

    def test_parse_af_system_prompt(self, spawner: LettaSpawner):
        files = {"agent.af": json.dumps(self._af_data())}
        result = spawner.parse(files)
        flow = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        system_texts = " ".join(m.text for m in flow)
        assert "research assistant" in system_texts

    def test_parse_af_tools(self, spawner: LettaSpawner):
        files = {"agent.af": json.dumps(self._af_data())}
        result = spawner.parse(files)
        assert len(result.skills) >= 1
        names = {s.name for s in result.skills}
        assert "search papers" in names

    def test_parse_af_tool_rules(self, spawner: LettaSpawner):
        files = {"agent.af": json.dumps(self._af_data())}
        result = spawner.parse(files)
        flow = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert any("tool_rules" in (m.source_file or "") for m in flow)

    def test_parse_af_messages(self, spawner: LettaSpawner):
        files = {"agent.af": json.dumps(self._af_data())}
        result = spawner.parse(files)
        state = [m for m in result.memory if m.label == MemoryLabel.STATE]
        assert len(state) >= 2
        assert any(m.timestamp is not None for m in state)

    def test_parse_af_env_vars(self, spawner: LettaSpawner):
        files = {"agent.af": json.dumps(self._af_data())}
        result = spawner.parse(files)
        ctx = [m for m in result.memory if "env_vars" in (m.source_file or "")]
        assert len(ctx) == 1
        assert "OPENAI_API_KEY" in ctx[0].text

    def test_parse_af_mcp_servers(self, spawner: LettaSpawner):
        files = {"agent.af": json.dumps(self._af_data())}
        result = spawner.parse(files)
        assert "arxiv" in result.mcp_configs

    def test_parse_af_model_config(self, spawner: LettaSpawner):
        files = {"agent.af": json.dumps(self._af_data())}
        result = spawner.parse(files)
        assert result.source_metadata.get("letta.model") == "gpt-4"

    def test_rejects_invalid_af(self, spawner: LettaSpawner, tmp_path: Path):
        af_path = tmp_path / "bad.af"
        af_path.write_text("not json")
        assert spawner.detect(af_path) is False

    def test_validate_af_file(self, spawner: LettaSpawner, tmp_path: Path):
        af_path = tmp_path / "agent.af"
        af_path.write_text(json.dumps(self._af_data()))
        report = spawner.validate(af_path)
        assert report.valid is True


class TestValidate:
    def test_valid_project(self, spawner: LettaSpawner, letta_project: Path):
        report = spawner.validate(letta_project)
        assert report.valid is True

    def test_empty_dir_warning(self, spawner: LettaSpawner, tmp_path: Path):
        report = spawner.validate(tmp_path)
        assert report.valid is True
        assert len(report.issues) == 1
        assert report.issues[0].level == "warning"

    def test_not_a_dir(self, spawner: LettaSpawner, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("hello")
        report = spawner.validate(f)
        assert report.valid is False

    def test_invalid_json(self, spawner: LettaSpawner, tmp_path: Path):
        (tmp_path / "agent_state.json").write_text("not json {{{")
        report = spawner.validate(tmp_path)
        assert report.valid is False
        assert any("Invalid JSON" in i.message for i in report.issues)

    def test_valid_db(self, spawner: LettaSpawner, letta_db_project: Path):
        db_path = letta_db_project / "agent.db"
        report = spawner.validate(db_path)
        assert report.valid is True
