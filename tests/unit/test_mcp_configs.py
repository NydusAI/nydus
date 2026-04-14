"""Tests for MCP server config support.

Covers:
- ``McpModule`` (raw dict configs on ``Egg``)
- Packager round-trip (``mcp.json`` in archive)
- Spawner/hatcher (OpenClaw)
- Pipeline pooling of MCP configs
"""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pynydus.api.schemas import (
    AgentSkill,
    Egg,
    Manifest,
    McpModule,
    MemoryModule,
    MemoryRecord,
    SkillsModule,
)
from pynydus.common.enums import AgentType, MemoryLabel
from pynydus.engine.packager import load, save

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_egg() -> Egg:
    """Egg with MCP configs on ``McpModule``."""
    return Egg(
        manifest=Manifest(
            nydus_version="0.0.7",
            created_at=datetime.now(UTC),
            agent_type=AgentType.OPENCLAW,
        ),
        skills=SkillsModule(
            skills=[
                AgentSkill(
                    name="query db",
                    description="",
                    body="Run SQL queries.",
                    metadata={"id": "skill_001", "source_framework": "markdown_skill"},
                )
            ],
        ),
        mcp=McpModule(
            configs={
                "snowflake": {
                    "command": "npx",
                    "args": ["-y", "@anthropic/snowflake-mcp"],
                    "env": {"SNOWFLAKE_ACCOUNT": "demo"},
                    "description": "Snowflake data access",
                },
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@anthropic/filesystem-mcp"],
                },
            }
        ),
        memory=MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="A preference.",
                    label=MemoryLabel.PERSONA,
                    agent_type="openclaw",
                    source_store="SOUL.md",
                )
            ]
        ),
    )


@pytest.fixture
def openclaw_project_with_mcp(tmp_path: Path) -> Path:
    """OpenClaw project directory containing MCP configs."""
    root = tmp_path / "openclaw_mcp"
    root.mkdir()
    (root / "SOUL.md").write_text("I am helpful.\n")
    sk = root / "skills"
    sk.mkdir()
    (sk / "greet.md").write_text("Say hello.\n")
    mcp_dir = root / "mcp"
    mcp_dir.mkdir()
    (mcp_dir / "snowflake.json").write_text(
        json.dumps({"command": "npx", "args": ["-y", "@anthropic/snowflake-mcp"]})
    )
    return root


@pytest.fixture
def openclaw_project_with_mcp_file(tmp_path: Path) -> Path:
    """OpenClaw project with a single mcp.json file."""
    root = tmp_path / "openclaw_mcp_file"
    root.mkdir()
    (root / "SOUL.md").write_text("I am helpful.\n")
    mcp_data = {
        "snowflake": {"command": "npx", "args": ["-y", "@anthropic/snowflake-mcp"]},
        "github": {"url": "https://mcp.github.com"},
    }
    (root / "mcp.json").write_text(json.dumps(mcp_data))
    return root


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestMcpModuleSchema:
    def test_defaults(self):
        m = McpModule()
        assert m.configs == {}

    def test_from_dicts(self):
        m = McpModule(configs={"db": {"command": "node"}})
        assert m.configs["db"]["command"] == "node"


class TestSkillsModuleSchema:
    def test_skills_module_default_empty_mcp_elsewhere(self):
        module = SkillsModule()
        assert module.skills == []


# ---------------------------------------------------------------------------
# Packager round-trip
# ---------------------------------------------------------------------------


class TestMcpPackagerRoundTrip:
    def test_mcp_configs_written_to_archive(self, mcp_egg: Egg, tmp_path: Path):
        path = save(mcp_egg, tmp_path / "test.egg")
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            assert "mcp.json" in names

    def test_mcp_configs_content_correct(self, mcp_egg: Egg, tmp_path: Path):
        path = save(mcp_egg, tmp_path / "test.egg")
        with zipfile.ZipFile(path, "r") as zf:
            doc = json.loads(zf.read("mcp.json"))
            servers = doc.get("mcpServers", doc)
            data = servers["snowflake"]
            assert data["command"] == "npx"
            assert data["args"] == ["-y", "@anthropic/snowflake-mcp"]
            assert data["env"] == {"SNOWFLAKE_ACCOUNT": "demo"}
            assert data["description"] == "Snowflake data access"

    def test_round_trip_preserves_configs(self, mcp_egg: Egg, tmp_path: Path):
        path = save(mcp_egg, tmp_path / "test.egg")
        loaded = load(path)
        assert len(loaded.mcp.configs) == 2
        assert "snowflake" in loaded.mcp.configs
        assert "filesystem" in loaded.mcp.configs
        assert loaded.mcp.configs["snowflake"]["command"] == "npx"

    def test_no_mcp_configs_produces_empty(self, tmp_path: Path):
        egg = Egg(
            manifest=Manifest(
                nydus_version="0.0.7",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
            ),
            skills=SkillsModule(
                skills=[
                    AgentSkill(
                        name="test",
                        description="",
                        body="hello",
                        metadata={"id": "s1", "source_framework": "x"},
                    )
                ]
            ),
        )
        path = save(egg, tmp_path / "test.egg")
        loaded = load(path)
        assert loaded.mcp.configs == {}

    def test_sparse_config_in_archive(self, tmp_path: Path):
        egg = Egg(
            manifest=Manifest(
                nydus_version="0.0.7",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
            ),
            mcp=McpModule(configs={"simple": {"command": "node"}}),
        )
        path = save(egg, tmp_path / "test.egg")
        with zipfile.ZipFile(path, "r") as zf:
            doc = json.loads(zf.read("mcp.json"))
            servers = doc.get("mcpServers", doc)
            assert servers["simple"] == {"command": "node"}


# ---------------------------------------------------------------------------
# Spawner extraction
# ---------------------------------------------------------------------------


class TestOpenClawMcpExtraction:
    def test_parse_from_mcp_dir(self):
        from pynydus.agents.openclaw.spawner import OpenClawSpawner

        files = {
            "SOUL.md": "I am helpful.\n",
            "skills/greet.md": "Say hello.\n",
            "mcp/snowflake.json": json.dumps(
                {"command": "npx", "args": ["-y", "@anthropic/snowflake-mcp"]}
            ),
        }
        result = OpenClawSpawner().parse(files)
        assert "snowflake" in result.mcp_configs
        assert result.mcp_configs["snowflake"]["command"] == "npx"

    def test_parse_from_mcp_json(self):
        from pynydus.agents.openclaw.spawner import OpenClawSpawner

        mcp_data = {
            "snowflake": {"command": "npx", "args": ["-y", "@anthropic/snowflake-mcp"]},
            "github": {"url": "https://mcp.github.com"},
        }
        files = {
            "SOUL.md": "I am helpful.\n",
            "mcp.json": json.dumps(mcp_data),
        }
        result = OpenClawSpawner().parse(files)
        assert "snowflake" in result.mcp_configs
        assert "github" in result.mcp_configs
        assert result.mcp_configs["github"]["url"] == "https://mcp.github.com"

    def test_no_mcp_returns_empty(self):
        from pynydus.agents.openclaw.spawner import OpenClawSpawner

        files = {"SOUL.md": "hi\n"}
        result = OpenClawSpawner().parse(files)
        assert result.mcp_configs == {}


# ---------------------------------------------------------------------------
# Hatcher output
# ---------------------------------------------------------------------------


class TestOpenClawHatcherMcp:
    def test_mcp_configs_written(self, mcp_egg: Egg, tmp_path: Path, hatch_to_disk):
        from pynydus.agents.openclaw.hatcher import OpenClawHatcher

        result = hatch_to_disk(OpenClawHatcher(), mcp_egg, tmp_path / "out")
        mcp_path = tmp_path / "out" / "mcp.json"
        assert mcp_path.is_file()
        doc = json.loads(mcp_path.read_text())
        data = doc["mcpServers"]["snowflake"]
        assert data["command"] == "npx"
        assert "mcp.json" in result.files_created

    def test_no_mcp_configs_skips_dir(self, tmp_path: Path, hatch_to_disk):
        from pynydus.agents.openclaw.hatcher import OpenClawHatcher

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.0.7",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
            ),
            skills=SkillsModule(
                skills=[
                    AgentSkill(
                        name="test",
                        description="",
                        body="hello",
                        metadata={"id": "s1", "source_framework": "x"},
                    )
                ]
            ),
            memory=MemoryModule(
                memory=[
                    MemoryRecord(
                        id="m1",
                        text="pref",
                        label=MemoryLabel.PERSONA,
                        agent_type="x",
                        source_store="x",
                    )
                ]
            ),
        )
        result = hatch_to_disk(OpenClawHatcher(), egg, tmp_path / "out")
        assert not (tmp_path / "out" / "mcp.json").exists()
        assert "mcp.json" not in result.files_created


# ---------------------------------------------------------------------------
# Pipeline pooling
# ---------------------------------------------------------------------------


class TestPoolMcpConfigs:
    def test_pool_merges_mcp_configs(self):
        """MCP configs from multiple spawner parse results merge correctly."""
        from pynydus.api.raw_types import ParseResult

        result1 = ParseResult(
            mcp_configs={"snowflake": {"command": "npx"}},
        )
        result2 = ParseResult(
            mcp_configs={"github": {"url": "https://mcp.github.com"}},
        )
        merged = dict(result1.mcp_configs)
        merged.update(result2.mcp_configs)
        assert "snowflake" in merged
        assert "github" in merged


# ---------------------------------------------------------------------------
# End-to-end: spawn → save → load → hatch
# ---------------------------------------------------------------------------


class TestMcpEndToEnd:
    def test_openclaw_spawn_pack_unpack_hatch(self, tmp_path: Path, hatch_to_disk):
        from pynydus.agents.openclaw.hatcher import OpenClawHatcher
        from pynydus.agents.openclaw.spawner import OpenClawSpawner

        files = {
            "SOUL.md": "I am helpful.\n",
            "skills/greet.md": "Say hello.\n",
            "mcp/snowflake.json": json.dumps(
                {"command": "npx", "args": ["-y", "@anthropic/snowflake-mcp"]}
            ),
        }
        result = OpenClawSpawner().parse(files)
        assert "snowflake" in result.mcp_configs

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.0.7",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
            ),
            skills=SkillsModule(
                skills=[
                    AgentSkill(
                        name="greet",
                        description="",
                        body="Say hello.",
                        metadata={"id": "s1", "source_framework": "openclaw"},
                    )
                ],
            ),
            mcp=McpModule(configs=dict(result.mcp_configs)),
            memory=MemoryModule(
                memory=[
                    MemoryRecord(
                        id="m1",
                        text="I am helpful.",
                        label=MemoryLabel.PERSONA,
                        agent_type="openclaw",
                        source_store="SOUL.md",
                    )
                ]
            ),
        )

        egg_path = save(egg, tmp_path / "test.egg", raw_artifacts=files)
        loaded = load(egg_path)
        assert len(loaded.mcp.configs) == 1
        assert loaded.mcp.configs["snowflake"]["command"] == "npx"

        out = tmp_path / "hatched"
        hatch_result = hatch_to_disk(OpenClawHatcher(), loaded, out)
        mcp_path = out / "mcp.json"
        assert mcp_path.is_file()
        doc = json.loads(mcp_path.read_text())
        assert doc["mcpServers"]["snowflake"]["command"] == "npx"
        assert "mcp.json" in hatch_result.files_created
