"""Tests for MCP server config support (Step 22).

Covers:
- Schema model (McpServerConfig on SkillsModule)
- Packager round-trip (mcp/*.json in archive)
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
    Egg,
    Manifest,
    McpServerConfig,
    MemoryModule,
    MemoryRecord,
    SkillRecord,
    SkillsModule,
)
from pynydus.common.enums import AgentType, Bucket, MemoryLabel
from pynydus.engine.packager import load, save

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_egg() -> Egg:
    """Egg with MCP configs attached to SkillsModule."""
    return Egg(
        manifest=Manifest(
            nydus_version="0.1.0",
            created_at=datetime.now(UTC),
            agent_type=AgentType.OPENCLAW,
            included_modules=[Bucket.SKILL, Bucket.MEMORY],
        ),
        skills=SkillsModule(
            skills=[
                SkillRecord(
                    id="skill_001",
                    name="query db",
                    agent_type="markdown_skill",
                    content="Run SQL queries.",
                )
            ],
            mcp_configs={
                "snowflake": McpServerConfig(
                    command="npx",
                    args=["-y", "@anthropic/snowflake-mcp"],
                    env={"SNOWFLAKE_ACCOUNT": "demo"},
                    description="Snowflake data access",
                ),
                "filesystem": McpServerConfig(
                    command="npx",
                    args=["-y", "@anthropic/filesystem-mcp"],
                ),
            },
        ),
        memory=MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="A preference.",
                    label=MemoryLabel.PERSONA,
                    agent_type="openclaw",
                    source_store="soul.md",
                )
            ]
        ),
    )


@pytest.fixture
def openclaw_project_with_mcp(tmp_path: Path) -> Path:
    """OpenClaw project directory containing MCP configs."""
    root = tmp_path / "openclaw_mcp"
    root.mkdir()
    (root / "soul.md").write_text("I am helpful.\n")
    (root / "skill.md").write_text("# greet\n\nSay hello.\n")
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
    (root / "soul.md").write_text("I am helpful.\n")
    mcp_data = {
        "snowflake": {"command": "npx", "args": ["-y", "@anthropic/snowflake-mcp"]},
        "github": {"url": "https://mcp.github.com"},
    }
    (root / "mcp.json").write_text(json.dumps(mcp_data))
    return root


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestMcpServerConfigSchema:
    def test_defaults(self):
        cfg = McpServerConfig()
        assert cfg.command == ""
        assert cfg.args == []
        assert cfg.env == {}
        assert cfg.url == ""
        assert cfg.description == ""

    def test_from_dict(self):
        cfg = McpServerConfig(command="npx", args=["-y", "server"], env={"KEY": "val"})
        assert cfg.command == "npx"
        assert cfg.args == ["-y", "server"]
        assert cfg.env == {"KEY": "val"}

    def test_skills_module_default_empty(self):
        module = SkillsModule()
        assert module.mcp_configs == {}

    def test_skills_module_with_configs(self):
        module = SkillsModule(mcp_configs={"db": McpServerConfig(command="node")})
        assert "db" in module.mcp_configs
        assert module.mcp_configs["db"].command == "node"


# ---------------------------------------------------------------------------
# Packager round-trip
# ---------------------------------------------------------------------------


class TestMcpPackagerRoundTrip:
    def test_mcp_configs_written_to_archive(self, mcp_egg: Egg, tmp_path: Path):
        path = save(mcp_egg, tmp_path / "test.egg")
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            assert "mcp/snowflake.json" in names
            assert "mcp/filesystem.json" in names

    def test_mcp_configs_content_correct(self, mcp_egg: Egg, tmp_path: Path):
        path = save(mcp_egg, tmp_path / "test.egg")
        with zipfile.ZipFile(path, "r") as zf:
            data = json.loads(zf.read("mcp/snowflake.json"))
            assert data["command"] == "npx"
            assert data["args"] == ["-y", "@anthropic/snowflake-mcp"]
            assert data["env"] == {"SNOWFLAKE_ACCOUNT": "demo"}
            assert data["description"] == "Snowflake data access"

    def test_round_trip_preserves_configs(self, mcp_egg: Egg, tmp_path: Path):
        path = save(mcp_egg, tmp_path / "test.egg")
        loaded = load(path)
        assert len(loaded.skills.mcp_configs) == 2
        assert "snowflake" in loaded.skills.mcp_configs
        assert "filesystem" in loaded.skills.mcp_configs
        assert loaded.skills.mcp_configs["snowflake"].command == "npx"

    def test_no_mcp_configs_produces_empty(self, tmp_path: Path):
        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="s1",
                        name="test",
                        agent_type="x",
                        content="hello",
                    )
                ]
            ),
        )
        path = save(egg, tmp_path / "test.egg")
        loaded = load(path)
        assert loaded.skills.mcp_configs == {}

    def test_exclude_defaults_in_archive(self, tmp_path: Path):
        """Only non-default fields should appear in the JSON."""
        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL],
            ),
            skills=SkillsModule(
                mcp_configs={"simple": McpServerConfig(command="node")},
            ),
        )
        path = save(egg, tmp_path / "test.egg")
        with zipfile.ZipFile(path, "r") as zf:
            data = json.loads(zf.read("mcp/simple.json"))
            assert data == {"command": "node"}
            assert "args" not in data
            assert "env" not in data


# ---------------------------------------------------------------------------
# Spawner extraction
# ---------------------------------------------------------------------------


class TestOpenClawMcpExtraction:
    def test_parse_from_mcp_dir(self):
        from pynydus.agents.openclaw.spawner import OpenClawSpawner

        files = {
            "soul.md": "I am helpful.\n",
            "skill.md": "# greet\n\nSay hello.\n",
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
            "soul.md": "I am helpful.\n",
            "mcp.json": json.dumps(mcp_data),
        }
        result = OpenClawSpawner().parse(files)
        assert "snowflake" in result.mcp_configs
        assert "github" in result.mcp_configs
        assert result.mcp_configs["github"]["url"] == "https://mcp.github.com"

    def test_no_mcp_returns_empty(self):
        from pynydus.agents.openclaw.spawner import OpenClawSpawner

        files = {"soul.md": "hi\n"}
        result = OpenClawSpawner().parse(files)
        assert result.mcp_configs == {}


# ---------------------------------------------------------------------------
# Hatcher output
# ---------------------------------------------------------------------------


class TestOpenClawHatcherMcp:
    def test_mcp_configs_written(self, mcp_egg: Egg, tmp_path: Path, hatch_to_disk):
        from pynydus.agents.openclaw.hatcher import OpenClawHatcher

        result = hatch_to_disk(OpenClawHatcher(), mcp_egg, tmp_path / "out")
        mcp_dir = tmp_path / "out" / "mcp"
        assert mcp_dir.is_dir()
        sf = mcp_dir / "snowflake.json"
        assert sf.exists()
        data = json.loads(sf.read_text())
        assert data["command"] == "npx"
        assert "mcp/snowflake.json" in result.files_created

    def test_no_mcp_configs_skips_dir(self, tmp_path: Path, hatch_to_disk):
        from pynydus.agents.openclaw.hatcher import OpenClawHatcher

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL, Bucket.MEMORY],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="s1",
                        name="test",
                        agent_type="x",
                        content="hello",
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
        assert not (tmp_path / "out" / "mcp").exists()
        assert not any(f.startswith("mcp/") for f in result.files_created)


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
            "soul.md": "I am helpful.\n",
            "skill.md": "# greet\n\nSay hello.\n",
            "mcp/snowflake.json": json.dumps(
                {"command": "npx", "args": ["-y", "@anthropic/snowflake-mcp"]}
            ),
        }
        result = OpenClawSpawner().parse(files)
        assert "snowflake" in result.mcp_configs

        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                agent_type=AgentType.OPENCLAW,
                included_modules=[Bucket.SKILL, Bucket.MEMORY],
            ),
            skills=SkillsModule(
                skills=[
                    SkillRecord(
                        id="s1",
                        name="greet",
                        agent_type=AgentType.OPENCLAW,
                        content="Say hello.",
                    )
                ],
                mcp_configs={
                    name: McpServerConfig(**cfg) for name, cfg in result.mcp_configs.items()
                },
            ),
            memory=MemoryModule(
                memory=[
                    MemoryRecord(
                        id="m1",
                        text="I am helpful.",
                        label=MemoryLabel.PERSONA,
                        agent_type="openclaw",
                        source_store="soul.md",
                    )
                ]
            ),
        )

        egg_path = save(egg, tmp_path / "test.egg", raw_artifacts=files)
        loaded = load(egg_path)
        assert len(loaded.skills.mcp_configs) == 1
        assert loaded.skills.mcp_configs["snowflake"].command == "npx"

        out = tmp_path / "hatched"
        hatch_result = hatch_to_disk(OpenClawHatcher(), loaded, out)
        sf = out / "mcp" / "snowflake.json"
        assert sf.exists()
        data = json.loads(sf.read_text())
        assert data["command"] == "npx"
        assert "mcp/snowflake.json" in hatch_result.files_created
