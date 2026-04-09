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
    """Legacy directory-based agent_state.json fixture."""
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


def _make_af_fixture() -> dict:
    """Build a real AgentFileSchema-shaped .af fixture."""
    return {
        "agents": [
            {
                "id": "agent-abc",
                "name": "research_bot",
                "system": "You are a research assistant. Be thorough.",
                "agent_type": "letta_v1_agent",
                "description": "A bot that helps with ML research.",
                "block_ids": ["blk-0", "blk-1"],
                "tool_ids": ["tool-0", "tool-1", "tool-2"],
                "tool_rules": [
                    {"type": "TerminalToolRule", "tool_name": "send_message"}
                ],
                "tags": ["research", "ml"],
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Hello, how can I help?"}],
                        "created_at": "2024-06-01T10:00:00Z",
                    },
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": "Search for transformers."}],
                        "created_at": "2024-06-01T10:01:00Z",
                    },
                ],
                "in_context_message_ids": [],
                "tool_exec_environment_variables": {"SEARCH_API_KEY": "sk-test-123"},
                "llm_config": {
                    "model": "gpt-4o",
                    "model_endpoint": "https://api.openai.com/v1",
                    "context_window": 128000,
                },
                "embedding_config": {
                    "embedding_model": "text-embedding-3-small",
                    "embedding_dim": 1536,
                },
            }
        ],
        "blocks": [
            {
                "id": "blk-0",
                "label": "persona",
                "value": "I specialize in machine learning research.",
                "limit": 5000,
                "is_template": False,
            },
            {
                "id": "blk-1",
                "label": "human",
                "value": "The user is a PhD student studying CV.",
                "limit": 5000,
                "is_template": False,
            },
        ],
        "tools": [
            {
                "id": "tool-0",
                "name": "send_message",
                "source_code": None,
                "tool_type": "letta_core",
                "source_type": "python",
                "json_schema": {"name": "send_message"},
            },
            {
                "id": "tool-1",
                "name": "conversation_search",
                "source_code": None,
                "tool_type": "letta_builtin",
                "source_type": "python",
                "json_schema": {"name": "conversation_search"},
            },
            {
                "id": "tool-2",
                "name": "search_papers",
                "source_code": "def search_papers(q: str) -> str:\n    return q\n",
                "tool_type": "custom",
                "source_type": "python",
                "json_schema": {"name": "search_papers"},
            },
        ],
        "groups": [],
        "files": [],
        "sources": [],
        "mcp_servers": [
            {"server_name": "filesystem", "command": "npx", "args": ["@modelcontextprotocol/server-filesystem"]}
        ],
        "skills": [
            {"name": "web_search", "files": {"SKILL.md": "# Web Search\nSearches the web."}, "source_url": ""}
        ],
        "metadata": {"version": "1.0"},
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
    """Tests for legacy agent_state.json directory-based parsing."""

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


class TestLettaParseAF:
    """Tests for real AgentFileSchema .af parsing."""

    def test_blocks_parsed(self, spawner):
        af = _make_af_fixture()
        result = spawner.parse({"agent.af": json.dumps(af)})
        persona = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert any("machine learning" in m.text for m in persona)
        ctx = [m for m in result.memory if m.label == MemoryLabel.CONTEXT]
        assert any("PhD student" in m.text for m in ctx)

    def test_system_prompt_from_agent(self, spawner):
        af = _make_af_fixture()
        result = spawner.parse({"agent.af": json.dumps(af)})
        flow = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert any("research assistant" in m.text for m in flow)

    def test_custom_tools_only(self, spawner):
        """Only custom tools (with source_code) become skills; built-ins are skipped."""
        af = _make_af_fixture()
        result = spawner.parse({"agent.af": json.dumps(af)})
        skill_names = {s.name for s in result.skills}
        assert "search papers" in skill_names
        assert "send message" not in skill_names
        assert "conversation search" not in skill_names

    def test_tool_rules_as_flow(self, spawner):
        af = _make_af_fixture()
        result = spawner.parse({"agent.af": json.dumps(af)})
        flow = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert any("tool_rules" in m.source_file for m in flow)

    def test_messages_as_state(self, spawner):
        """Messages with content list [{type, text}] are parsed as STATE."""
        af = _make_af_fixture()
        result = spawner.parse({"agent.af": json.dumps(af)})
        state = [m for m in result.memory if m.label == MemoryLabel.STATE]
        texts = [m.text for m in state]
        assert any("Hello" in t for t in texts)
        assert any("transformers" in t for t in texts)

    def test_messages_have_timestamps(self, spawner):
        af = _make_af_fixture()
        result = spawner.parse({"agent.af": json.dumps(af)})
        state = [m for m in result.memory if m.label == MemoryLabel.STATE]
        assert any(m.timestamp is not None for m in state)

    def test_env_vars_as_context(self, spawner):
        af = _make_af_fixture()
        result = spawner.parse({"agent.af": json.dumps(af)})
        ctx = [m for m in result.memory if m.label == MemoryLabel.CONTEXT]
        assert any("SEARCH_API_KEY" in m.text for m in ctx)

    def test_mcp_servers(self, spawner):
        af = _make_af_fixture()
        result = spawner.parse({"agent.af": json.dumps(af)})
        assert "filesystem" in result.mcp_configs

    def test_skills_field(self, spawner):
        """Top-level skills with SKILL.md files are parsed."""
        af = _make_af_fixture()
        result = spawner.parse({"agent.af": json.dumps(af)})
        skill_names = {s.name for s in result.skills}
        assert "web_search" in skill_names

    def test_model_config_metadata(self, spawner):
        af = _make_af_fixture()
        result = spawner.parse({"agent.af": json.dumps(af)})
        assert result.source_metadata.get("letta.llm.model") == "gpt-4o"
        assert "letta.embedding.embedding_model" in result.source_metadata

    def test_agent_metadata(self, spawner):
        af = _make_af_fixture()
        result = spawner.parse({"agent.af": json.dumps(af)})
        assert result.source_metadata.get("letta.agent_type") == "letta_v1_agent"
        assert "letta.tags" in result.source_metadata

    def test_expanded_block_labels(self, spawner):
        """Expanded labels like 'soul', 'about_user', 'scratchpad' map correctly."""
        af = _make_af_fixture()
        af["blocks"] = [
            {"id": "b0", "label": "soul", "value": "I am a soul.", "limit": 5000},
            {"id": "b1", "label": "about_user", "value": "User info.", "limit": 5000},
            {"id": "b2", "label": "scratchpad", "value": "working notes", "limit": 5000},
            {"id": "b3", "label": "custom_instructions", "value": "Be brief.", "limit": 5000},
        ]
        result = spawner.parse({"agent.af": json.dumps(af)})
        persona = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert any("soul" in m.text for m in persona)
        ctx = [m for m in result.memory if m.label == MemoryLabel.CONTEXT]
        assert any("User info" in m.text for m in ctx)
        state = [m for m in result.memory if m.label == MemoryLabel.STATE]
        assert any("working notes" in m.text for m in state)
        flow = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert any("Be brief" in m.text for m in flow)

    def test_af_bad_json_falls_through(self, spawner):
        """Bad .af JSON falls through to legacy parsing."""
        files = {"agent.af": "NOT JSON", "system_prompt.md": "You are helpful."}
        result = spawner.parse(files)
        flow = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert any("helpful" in m.text for m in flow)

    def test_af_without_agents_key_falls_through(self, spawner):
        """An .af without top-level 'agents' falls through to legacy parsing."""
        files = {
            "agent.af": json.dumps({"memory": {"persona": "old format"}}),
            "system_prompt.md": "You are helpful.",
        }
        result = spawner.parse(files)
        flow = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert any("helpful" in m.text for m in flow)


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

    def test_af_file(self, tmp_path: Path, spawner):
        af = _make_af_fixture()
        af_path = tmp_path / "agent.af"
        af_path.write_text(json.dumps(af))
        assert spawner.detect(af_path) is True

    def test_af_in_dir(self, tmp_path: Path, spawner):
        af = _make_af_fixture()
        (tmp_path / "agent.af").write_text(json.dumps(af))
        assert spawner.detect(tmp_path) is True


class TestLettaRender:
    def test_af_output(self, hatcher):
        """Hatcher produces agent.af as primary output."""
        egg = _rich_egg()
        result = hatcher.render(egg)
        assert "agent.af" in result.files
        af = json.loads(result.files["agent.af"])
        assert "agents" in af
        assert "blocks" in af
        assert "tools" in af

    def test_agent_structure(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        af = json.loads(result.files["agent.af"])
        agent = af["agents"][0]
        assert agent["name"] == "nydus_agent"
        assert "system" in agent
        assert isinstance(agent["block_ids"], list)
        assert isinstance(agent["tool_ids"], list)

    def test_system_prompt_in_agent(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        af = json.loads(result.files["agent.af"])
        agent = af["agents"][0]
        assert "Be helpful" in agent["system"]

    def test_persona_block(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        af = json.loads(result.files["agent.af"])
        persona_blocks = [b for b in af["blocks"] if b["label"] == "persona"]
        assert len(persona_blocks) == 1
        assert "I study ML" in persona_blocks[0]["value"]

    def test_human_block(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        af = json.loads(result.files["agent.af"])
        human_blocks = [b for b in af["blocks"] if b["label"] == "human"]
        assert len(human_blocks) == 1
        assert "PhD student" in human_blocks[0]["value"]

    def test_tools_as_custom(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        af = json.loads(result.files["agent.af"])
        assert len(af["tools"]) >= 1
        tool = af["tools"][0]
        assert tool["tool_type"] == "custom"
        assert tool["source_code"] is not None
        assert "greet" in tool["name"]

    def test_archival_supplemental(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        entries = json.loads(result.files["archival_memory.json"])
        assert len(entries) >= 1

    def test_no_legacy_files(self, hatcher):
        """No legacy agent_state.json, system_prompt.md, or tools/ directory."""
        egg = _rich_egg()
        result = hatcher.render(egg)
        assert "agent_state.json" not in result.files
        assert "system_prompt.md" not in result.files
        assert not any(f.startswith("tools/") for f in result.files)
        assert ".letta/config.json" not in result.files

    def test_credentials_in_env_vars(self, hatcher):
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
        af = json.loads(result.files["agent.af"])
        env_vars = af["agents"][0]["tool_exec_environment_variables"]
        assert env_vars["API_KEY"] == "{{SECRET_001}}"

    def test_metadata(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        af = json.loads(result.files["agent.af"])
        assert "metadata" in af
        assert af["metadata"]["nydus_source"] == "letta"

    def test_empty_egg(self, hatcher):
        egg = make_egg(skills=[], memory=[])
        result = hatcher.render(egg)
        af = json.loads(result.files["agent.af"])
        assert af["tools"] == []
        assert af["blocks"] == []
        agent = af["agents"][0]
        assert agent["system"] == ""
