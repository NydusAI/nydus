"""Contract tests for ZeroClaw spawner and hatcher."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pynydus.agents.zeroclaw.hatcher import ZeroClawHatcher
from pynydus.agents.zeroclaw.spawner import ZeroClawSpawner
from pynydus.api.schemas import MemoryRecord, SkillRecord
from pynydus.common.enums import MemoryLabel

from conftest import make_egg


@pytest.fixture
def spawner():
    return ZeroClawSpawner()


@pytest.fixture
def hatcher():
    return ZeroClawHatcher()


@pytest.fixture
def zc_files():
    return {
        "SOUL.md": "I am a personal AI assistant.\n\nI value efficiency.",
        "IDENTITY.md": "My name is ZeroClaw Agent.",
        "AGENTS.md": "Follow structured output. Always cite sources.",
        "USER.md": "User prefers Rust and systems programming.",
        "MEMORY.md": "Learned about async patterns yesterday.",
        "memory/2026-03-15.md": "Discussed Tokio runtime with user.",
        "tools/search_web.py": (
            'def search_web(query: str) -> str:\n    """Search the web."""\n    return query\n'
        ),
        "config.toml": '[agent]\nmodel = "claude-3"\nname = "zc-agent"\n',
    }


def _rich_egg():
    return make_egg(
        skills=[
            SkillRecord(id="s1", name="search", agent_type="zeroclaw", content="def search(): pass")
        ],
        memory=[
            MemoryRecord(
                id="m1",
                text="I am helpful.",
                label=MemoryLabel.PERSONA,
                agent_type="zeroclaw",
                source_store="SOUL.md",
            ),
            MemoryRecord(
                id="m2",
                text="Follow rules.",
                label=MemoryLabel.FLOW,
                agent_type="zeroclaw",
                source_store="AGENTS.md",
            ),
            MemoryRecord(
                id="m3",
                text="User likes Rust.",
                label=MemoryLabel.CONTEXT,
                agent_type="zeroclaw",
                source_store="USER.md",
            ),
            MemoryRecord(
                id="m4",
                text="A stored fact.",
                label=MemoryLabel.STATE,
                agent_type="zeroclaw",
                source_store="MEMORY.md",
            ),
        ],
    )


def _rich_egg_with_splits():
    """Egg with IDENTITY, TOOLS, dated memory — tests file-splitting logic."""
    return make_egg(
        skills=[
            SkillRecord(
                id="s1", name="search web", agent_type="zeroclaw", content="def search(): pass"
            ),
            SkillRecord(
                id="s2", name="file read", agent_type="zeroclaw", content="def file_read(): pass"
            ),
        ],
        memory=[
            MemoryRecord(
                id="m1",
                text="I am a personal assistant.",
                label=MemoryLabel.PERSONA,
                agent_type="zeroclaw",
                source_store="SOUL.md",
            ),
            MemoryRecord(
                id="m2",
                text="ZeroClaw Agent v2",
                label=MemoryLabel.PERSONA,
                agent_type="zeroclaw",
                source_store="IDENTITY.md",
            ),
            MemoryRecord(
                id="m3",
                text="Follow structured output.",
                label=MemoryLabel.FLOW,
                agent_type="zeroclaw",
                source_store="AGENTS.md",
            ),
            MemoryRecord(
                id="m4",
                text="User likes Rust.",
                label=MemoryLabel.CONTEXT,
                agent_type="zeroclaw",
                source_store="USER.md",
            ),
            MemoryRecord(
                id="m5",
                text="Rate limit 100 req/min for search API.",
                label=MemoryLabel.CONTEXT,
                agent_type="zeroclaw",
                source_store="TOOLS.md",
            ),
            MemoryRecord(
                id="m6",
                text="Async patterns are preferred.",
                label=MemoryLabel.STATE,
                agent_type="zeroclaw",
                source_store="MEMORY.md",
            ),
            MemoryRecord(
                id="m7",
                text="Discussed Tokio runtime.",
                label=MemoryLabel.STATE,
                agent_type="zeroclaw",
                source_store="memory/2026-03-15.md",
                timestamp=datetime(2026, 3, 15, tzinfo=timezone.utc),
            ),
            MemoryRecord(
                id="m8",
                text="Configured async executor.",
                label=MemoryLabel.STATE,
                agent_type="zeroclaw",
                source_store="memory/2026-03-17.md",
                timestamp=datetime(2026, 3, 17, tzinfo=timezone.utc),
            ),
        ],
    )


def _cross_platform_egg():
    """Egg from a non-ZeroClaw source (e.g. Letta) — no ZeroClaw source_store hints."""
    return make_egg(
        skills=[
            SkillRecord(id="s1", name="analyze", agent_type="letta", content="def analyze(): pass")
        ],
        memory=[
            MemoryRecord(
                id="m1",
                text="I am a data analyst.",
                label=MemoryLabel.PERSONA,
                agent_type="letta",
                source_store="db.blocks.persona",
            ),
            MemoryRecord(
                id="m2",
                text="Be concise.",
                label=MemoryLabel.FLOW,
                agent_type="letta",
                source_store="agent_state.json#system",
            ),
            MemoryRecord(
                id="m3",
                text="User prefers Python.",
                label=MemoryLabel.CONTEXT,
                agent_type="letta",
                source_store="db.blocks.human",
            ),
            MemoryRecord(
                id="m4",
                text="Historical fact.",
                label=MemoryLabel.STATE,
                agent_type="letta",
                source_store="db.archival_memory",
            ),
        ],
    )


class TestZeroClawParse:
    def test_soul_persona(self, spawner, zc_files):
        result = spawner.parse(zc_files)
        persona = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert any(m.source_file == "SOUL.md" for m in persona)

    def test_identity_persona(self, spawner, zc_files):
        result = spawner.parse(zc_files)
        persona = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert any(m.source_file == "IDENTITY.md" for m in persona)

    def test_identity_json(self, spawner):
        files = {
            "identity.json": json.dumps(
                {
                    "name": "TestBot",
                    "personality": "Helpful and kind",
                    "backstory": "Created for testing",
                }
            )
        }
        result = spawner.parse(files)
        persona = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert "TestBot" in persona[0].text

    def test_agents_flow(self, spawner, zc_files):
        result = spawner.parse(zc_files)
        flow = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert any(m.source_file == "AGENTS.md" for m in flow)

    def test_user_context(self, spawner, zc_files):
        result = spawner.parse(zc_files)
        ctx = [m for m in result.memory if m.label == MemoryLabel.CONTEXT]
        assert any(m.source_file == "USER.md" for m in ctx)

    def test_memory_state(self, spawner, zc_files):
        result = spawner.parse(zc_files)
        state = [m for m in result.memory if m.label == MemoryLabel.STATE]
        assert any(m.source_file == "MEMORY.md" for m in state)

    def test_dated_memory(self, spawner, zc_files):
        result = spawner.parse(zc_files)
        dated = [m for m in result.memory if m.source_file == "memory/2026-03-15.md"]
        assert dated[0].timestamp is not None

    def test_tools_py(self, spawner, zc_files):
        result = spawner.parse(zc_files)
        assert any(s.source_file == "tools/search_web.py" for s in result.skills)

    def test_tools_json(self, spawner):
        files = {
            "tools.json": json.dumps(
                [{"name": "calculator", "description": "Compute math expressions"}]
            )
        }
        result = spawner.parse(files)
        assert any(s.name == "calculator" for s in result.skills)

    def test_config_toml(self, spawner, zc_files):
        result = spawner.parse(zc_files)
        assert "zeroclaw.agent.model" in result.source_metadata

    def test_empty(self, spawner):
        result = spawner.parse({})
        assert len(result.skills) == 0
        assert len(result.memory) == 0

    def test_identity_json_malformed(self, spawner):
        files = {"identity.json": "NOT VALID JSON"}
        result = spawner.parse(files)
        persona = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert len(persona) == 0

    def test_tools_json_missing_name(self, spawner):
        files = {
            "tools.json": json.dumps(
                [{"description": "no name field"}, {"name": "valid", "description": "ok"}]
            )
        }
        result = spawner.parse(files)
        assert len(result.skills) == 1
        assert result.skills[0].name == "valid"

    def test_tools_json_invalid(self, spawner):
        files = {"tools.json": "<<<NOT JSON>>>"}
        result = spawner.parse(files)
        assert len(result.skills) == 0

    def test_config_toml_malformed(self, spawner):
        files = {"config.toml": "[[[ bad toml"}
        result = spawner.parse(files)
        assert result.source_metadata == {} or isinstance(result.source_metadata, dict)


class TestZeroClawParseDB:
    def test_sqlite(self, spawner, tmp_path: Path):
        db_path = tmp_path / "memory.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE memory_entries (content TEXT, category TEXT, created_at TEXT)")
        conn.execute(
            "INSERT INTO memory_entries VALUES ('Core fact.', 'Core', '2026-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO memory_entries VALUES ('Daily note.', 'Daily', '2026-01-02T00:00:00')"
        )
        conn.commit()
        conn.close()
        result = spawner.parse_db(db_path)
        assert len(result.memory) == 2

    def test_sqlite_bad_rows(self, spawner, tmp_path: Path):
        db_path = tmp_path / "memory.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE memory_entries (content TEXT, category TEXT, created_at TEXT)")
        conn.execute("INSERT INTO memory_entries VALUES (NULL, 'Core', '2026-01-01')")
        conn.execute("INSERT INTO memory_entries VALUES ('', 'Daily', '2026-01-02')")
        conn.execute("INSERT INTO memory_entries VALUES ('Valid.', 'Core', '2026-01-03')")
        conn.commit()
        conn.close()
        result = spawner.parse_db(db_path)
        assert len(result.memory) == 1
        assert result.memory[0].text == "Valid."


class TestZeroClawDetect:
    def test_marker_dir(self, tmp_path: Path, spawner):
        (tmp_path / ".zeroclaw").mkdir()
        assert spawner.detect(tmp_path) is True


class TestZeroClawRender:
    def test_filenames(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        for f in ("persona.md", "knowledge.md", "agents.md", "user.md"):
            assert f in result.files

    def test_zeroclaw_marker(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        assert ".zeroclaw/.keep" in result.files

    def test_tools(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        assert any(f.startswith("tools/") for f in result.files)

    def test_identity_split(self, hatcher):
        egg = _rich_egg_with_splits()
        result = hatcher.render(egg)
        assert "persona.md" in result.files
        assert "identity.md" in result.files
        assert "ZeroClaw Agent v2" in result.files["identity.md"]
        assert "I am a personal assistant." in result.files["persona.md"]

    def test_tools_split(self, hatcher):
        egg = _rich_egg_with_splits()
        result = hatcher.render(egg)
        assert "user.md" in result.files
        assert "tools.md" in result.files
        assert "Rate limit" in result.files["tools.md"]
        assert "User likes Rust." in result.files["user.md"]

    def test_dated_memory(self, hatcher):
        egg = _rich_egg_with_splits()
        result = hatcher.render(egg)
        assert "knowledge.md" in result.files
        assert "memory/2026-03-15.md" in result.files
        assert "memory/2026-03-17.md" in result.files
        assert "Tokio runtime" in result.files["memory/2026-03-15.md"]
        assert "Async patterns" in result.files["knowledge.md"]

    def test_cross_platform_fallback(self, hatcher):
        egg = _cross_platform_egg()
        result = hatcher.render(egg)
        assert "persona.md" in result.files
        assert "agents.md" in result.files
        assert "user.md" in result.files
        assert "knowledge.md" in result.files
        assert "tools/analyze.py" in result.files
        assert "identity.md" not in result.files
        assert "tools.md" not in result.files

    def test_credentials_toml(self, hatcher):
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
        assert "config.toml" in result.files
        assert "config.json" not in result.files
        assert "{{SECRET_001}}" in result.files["config.toml"]
        assert "API_KEY" in result.files["config.toml"]

    def test_source_metadata_roundtrip(self, hatcher):
        egg = _rich_egg()
        egg.manifest.source_metadata = {
            "zeroclaw.agent.name": "zc-agent",
            "zeroclaw.agent.model": "claude-3",
        }
        result = hatcher.render(egg)
        assert "config.toml" in result.files
        toml = result.files["config.toml"]
        assert 'name = "zc-agent"' in toml
        assert 'model = "claude-3"' in toml

    def test_multiple_skills_separate_files(self, hatcher):
        egg = _rich_egg_with_splits()
        result = hatcher.render(egg)
        assert "tools/search_web.py" in result.files
        assert "tools/file_read.py" in result.files

    def test_empty_produces_marker_only(self, hatcher):
        egg = make_egg(skills=[], memory=[])
        result = hatcher.render(egg)
        assert ".zeroclaw/.keep" in result.files
        md_files = [f for f in result.files if f.endswith(".md")]
        assert len(md_files) == 0

    def test_no_uppercase_filenames(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        md_files = [f for f in result.files if f.endswith(".md")]
        for f in md_files:
            basename = f.split("/")[-1]
            assert basename == basename.lower(), f"Expected lowercase filename, got {f}"
