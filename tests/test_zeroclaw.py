"""Tests for ZeroClaw spawner and hatcher (Step 21)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pynydus.api.schemas import (
    Egg,
    InjectionMode,
    Manifest,
    MemoryLabel,
    MemoryModule,
    MemoryRecord,
    SecretKind,
    SecretRecord,
    SecretsModule,
    SkillRecord,
    SkillsModule,
    SourceType,
)
from pynydus.agents.zeroclaw.spawner import ZeroClawSpawner
from pynydus.agents.zeroclaw.hatcher import ZeroClawHatcher
from pynydus.engine.pipeline import _get_spawner
from pynydus.engine.hatcher import _get_hatcher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def zeroclaw_project(tmp_path: Path) -> Path:
    """Create a minimal ZeroClaw project directory."""
    src = tmp_path / "zeroclaw_src"
    src.mkdir()
    (src / "persona.md").write_text("I am a helpful coding assistant.\n")
    (src / "agents.md").write_text("Always be concise.\n\nUse code examples.\n")
    (src / "user.md").write_text("The user prefers Python.\n")

    tools_dir = src / "tools"
    tools_dir.mkdir()
    (tools_dir / "search.py").write_text("def search(query: str) -> str:\n    pass\n")
    (tools_dir / "calculate.py").write_text("def calculate(expr: str) -> float:\n    pass\n")

    (src / "config.json").write_text(json.dumps({"api_key": "sk-test-123"}) + "\n")
    return src


@pytest.fixture
def zeroclaw_egg() -> Egg:
    """Create a sample ZeroClaw egg for hatching tests."""
    return Egg(
        manifest=Manifest(
            nydus_version="0.1.0",
            created_at=datetime.now(UTC),
            source_type=SourceType.ZEROCLAW,
            included_modules=["skills", "memory", "secrets"],
        ),
        skills=SkillsModule(
            skills=[
                SkillRecord(
                    id="skill_001",
                    name="search",
                    source_type="zeroclaw",
                    content="def search(q): pass",
                ),
            ]
        ),
        memory=MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="I am a coding assistant.",
                    label=MemoryLabel.PERSONA,
                    source_framework="zeroclaw",
                    source_store="persona.md",
                ),
                MemoryRecord(
                    id="mem_002",
                    text="Be concise.",
                    label=MemoryLabel.FLOW,
                    source_framework="zeroclaw",
                    source_store="agents.md",
                ),
                MemoryRecord(
                    id="mem_003",
                    text="User prefers Python.",
                    label=MemoryLabel.CONTEXT,
                    source_framework="zeroclaw",
                    source_store="user.md",
                ),
            ]
        ),
        secrets=SecretsModule(
            secrets=[
                SecretRecord(
                    id="secret_001",
                    placeholder="{{API_KEY}}",
                    kind=SecretKind.CREDENTIAL,
                    name="API_KEY",
                    required_at_hatch=True,
                    injection_mode=InjectionMode.ENV,
                ),
            ]
        ),
    )


# ---------------------------------------------------------------------------
# ZeroClawSpawner tests
# ---------------------------------------------------------------------------


class TestZeroClawSpawnerDetect:
    def test_detects_with_persona(self, zeroclaw_project: Path):
        assert ZeroClawSpawner().detect(zeroclaw_project) is True

    def test_detects_with_marker(self, tmp_path: Path):
        src = tmp_path / "zc"
        src.mkdir()
        (src / ".zeroclaw").mkdir()
        assert ZeroClawSpawner().detect(src) is True

    def test_rejects_file(self, tmp_path: Path):
        f = tmp_path / "notdir.txt"
        f.write_text("hi")
        assert ZeroClawSpawner().detect(f) is False

    def test_rejects_empty_dir(self, tmp_path: Path):
        d = tmp_path / "empty"
        d.mkdir()
        assert ZeroClawSpawner().detect(d) is False


class TestZeroClawSpawnerParse:
    def _files(self) -> dict[str, str]:
        return {
            "persona.md": "I am a helpful coding assistant.\n",
            "agents.md": "Always be concise.\n\nUse code examples.\n",
            "user.md": "The user prefers Python.\n",
            "tools/search.py": "def search(query: str) -> str:\n    pass\n",
            "tools/calculate.py": "def calculate(expr: str) -> float:\n    pass\n",
            "config.json": json.dumps({"api_key": "sk-test-123"}) + "\n",
        }

    def test_parse_memories(self):
        result = ZeroClawSpawner().parse(self._files())
        assert len(result.memory) >= 3
        labels = {m.label for m in result.memory}
        assert MemoryLabel.PERSONA in labels
        assert MemoryLabel.FLOW in labels
        assert MemoryLabel.CONTEXT in labels

    def test_parse_skills(self):
        result = ZeroClawSpawner().parse(self._files())
        assert len(result.skills) == 2
        names = {s.name for s in result.skills}
        assert "search" in names
        assert "calculate" in names


class TestZeroClawSpawnerIdentityJson:
    def test_parse_identity_json(self):
        files = {
            "identity.json": json.dumps({
                "name": "Maya",
                "description": "A customer support agent",
                "personality": "empathetic and thorough",
            }),
        }
        result = ZeroClawSpawner().parse(files)
        persona = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert len(persona) == 1
        assert "Maya" in persona[0].text
        assert "empathetic" in persona[0].text

    def test_identity_json_combined_with_persona_md(self):
        files = {
            "persona.md": "I am a helpful assistant.\n",
            "identity.json": json.dumps({"name": "Bot", "role": "support agent"}),
        }
        result = ZeroClawSpawner().parse(files)
        persona = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert len(persona) >= 2


class TestZeroClawSpawnerConfigToml:
    def test_parse_config_toml_metadata(self):
        files = {
            "persona.md": "I am a bot.\n",
            "config.toml": 'name = "my-agent"\nmodel = "gpt-4"\n',
        }
        result = ZeroClawSpawner().parse(files)
        assert result.source_metadata.get("zeroclaw.name") == "my-agent"
        assert result.source_metadata.get("zeroclaw.model") == "gpt-4"


class TestZeroClawSpawnerMemoryDB:
    def test_parse_db_extracts_memories(self, tmp_path: Path):
        db_path = tmp_path / "memory.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE memory_entries (content TEXT, category TEXT, created_at TEXT)")
        conn.execute(
            "INSERT INTO memory_entries VALUES (?, ?, ?)",
            ("User prefers dark mode.", "core", "2026-03-01T12:00:00"),
        )
        conn.execute(
            "INSERT INTO memory_entries VALUES (?, ?, ?)",
            ("Had a meeting about project X.", "daily", "2026-03-15T09:00:00"),
        )
        conn.commit()
        conn.close()

        result = ZeroClawSpawner().parse_db(db_path)
        assert len(result.memory) == 2
        assert all(m.label == MemoryLabel.STATE for m in result.memory)
        assert result.memory[0].timestamp is not None

    def test_parse_db_with_supplemental_files(self, tmp_path: Path):
        db_path = tmp_path / "memory.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE memory_entries (content TEXT, category TEXT)")
        conn.execute("INSERT INTO memory_entries VALUES (?, ?)", ("A fact.", "core"))
        conn.commit()
        conn.close()

        supplemental = {"persona.md": "I am a helper.\n"}
        result = ZeroClawSpawner().parse_db(db_path, supplemental_files=supplemental)
        labels = {m.label for m in result.memory}
        assert MemoryLabel.STATE in labels
        assert MemoryLabel.PERSONA in labels

    def test_detect_memory_db(self, tmp_path: Path):
        src = tmp_path / "zc"
        src.mkdir()
        db_path = src / "memory.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE memory_entries (content TEXT)")
        conn.commit()
        conn.close()
        assert ZeroClawSpawner().detect(src) is True


class TestZeroClawSpawnerValidate:
    def test_valid_project(self, zeroclaw_project: Path):
        report = ZeroClawSpawner().validate(zeroclaw_project)
        assert report.valid is True

    def test_warns_sparse(self, tmp_path: Path):
        d = tmp_path / "sparse"
        d.mkdir()
        report = ZeroClawSpawner().validate(d)
        assert any("sparse" in i.message.lower() for i in report.issues)


# ---------------------------------------------------------------------------
# ZeroClawHatcher tests
# ---------------------------------------------------------------------------


class TestZeroClawHatcher:
    def test_hatch_produces_persona(self, zeroclaw_egg: Egg, tmp_path: Path):
        out = tmp_path / "hatched"
        result = ZeroClawHatcher().hatch(zeroclaw_egg, out)
        assert "persona.md" in result.files_created
        assert (out / "persona.md").read_text().strip() == "I am a coding assistant."

    def test_hatch_produces_agents(self, zeroclaw_egg: Egg, tmp_path: Path):
        out = tmp_path / "hatched"
        result = ZeroClawHatcher().hatch(zeroclaw_egg, out)
        assert "agents.md" in result.files_created

    def test_hatch_produces_user(self, zeroclaw_egg: Egg, tmp_path: Path):
        out = tmp_path / "hatched"
        result = ZeroClawHatcher().hatch(zeroclaw_egg, out)
        assert "user.md" in result.files_created

    def test_hatch_produces_tools(self, zeroclaw_egg: Egg, tmp_path: Path):
        out = tmp_path / "hatched"
        result = ZeroClawHatcher().hatch(zeroclaw_egg, out)
        tool_files = [f for f in result.files_created if f.startswith("tools/")]
        assert len(tool_files) == 1

    def test_hatch_produces_config(self, zeroclaw_egg: Egg, tmp_path: Path):
        out = tmp_path / "hatched"
        result = ZeroClawHatcher().hatch(zeroclaw_egg, out)
        assert "config.json" in result.files_created
        config = json.loads((out / "config.json").read_text())
        assert "API_KEY" in config

    def test_hatch_creates_marker(self, zeroclaw_egg: Egg, tmp_path: Path):
        out = tmp_path / "hatched"
        ZeroClawHatcher().hatch(zeroclaw_egg, out)
        assert (out / ".zeroclaw").is_dir()

    def test_hatch_target(self, zeroclaw_egg: Egg, tmp_path: Path):
        out = tmp_path / "hatched"
        result = ZeroClawHatcher().hatch(zeroclaw_egg, out)
        assert result.target == "zeroclaw"


# ---------------------------------------------------------------------------
# Dispatcher wiring
# ---------------------------------------------------------------------------


class TestDispatcherWiring:
    def test_get_spawner_zeroclaw(self):
        spawner = _get_spawner(SourceType.ZEROCLAW)
        assert isinstance(spawner, ZeroClawSpawner)

    def test_get_hatcher_zeroclaw(self):
        hatcher = _get_hatcher("zeroclaw")
        assert isinstance(hatcher, ZeroClawHatcher)
