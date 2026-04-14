"""Data-model invariants.

Guards against re-introducing deleted fields and verifies structural
contracts: Spawner/Hatcher ABCs, McpModule raw storage, AgentSkill
as the canonical skill type, and typed Egg artifact fields.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import make_egg
from pynydus.api.protocols import Hatcher, Spawner
from pynydus.api.raw_types import ParseResult, RenderResult
from pynydus.api.schemas import (
    AgentSkill,
    Manifest,
    McpModule,
    MemoryRecord,
)
from pynydus.common.enums import Bucket, ModuleType


# =====================================================================
# Deleted-field guardrails
# =====================================================================


class TestDeletedFields:
    """Ensure removed fields never resurface on the data models."""

    def test_manifest_no_source_metadata(self):
        assert "source_metadata" not in Manifest.model_fields

    def test_manifest_no_included_modules(self):
        assert "included_modules" not in Manifest.model_fields

    def test_memory_record_no_metadata(self):
        assert "metadata" not in MemoryRecord.model_fields

    def test_no_skill_record_type(self):
        from pynydus.api import schemas
        assert not hasattr(schemas, "SkillRecord")

    def test_parse_result_no_source_metadata(self):
        assert "source_metadata" not in ParseResult.model_fields


# =====================================================================
# McpModule
# =====================================================================


class TestMcpModule:
    def test_arbitrary_keys_preserved(self):
        raw = {
            "custom": {
                "command": "python",
                "env": {"FOO": "bar"},
                "custom_field": [1, 2, 3],
            }
        }
        m = McpModule(configs=raw)
        assert m.configs["custom"]["custom_field"] == [1, 2, 3]
        assert m.configs["custom"]["env"]["FOO"] == "bar"

    def test_egg_with_mcp(self):
        mcp = McpModule(configs={"srv": {"command": "node"}})
        egg = make_egg(mcp=mcp)
        assert egg.mcp.configs["srv"]["command"] == "node"


# =====================================================================
# AgentSkill (canonical type, no SkillRecord layer)
# =====================================================================


class TestAgentSkill:
    def test_metadata_stores_nydus_id(self):
        s = AgentSkill(
            name="test",
            description="Test.",
            body="Body.",
            metadata={"id": "skill_001", "agent_type": "openclaw"},
        )
        assert s.metadata["id"] == "skill_001"

    def test_render_roundtrip(self):
        from pynydus.api.skill_format import render_skill_md

        skill = AgentSkill(
            name="greet", description="Greets users.", body="Say hello warmly.", version="1.0",
        )
        md = render_skill_md(skill)
        assert "greet" in md
        assert "Say hello warmly." in md


# =====================================================================
# Spawner / Hatcher ABC protocols
# =====================================================================


class TestSpawnerHatcherProtocols:
    def test_spawner_is_abstract(self):
        with pytest.raises(TypeError, match="abstract"):
            Spawner()  # type: ignore[abstract]

    def test_hatcher_is_abstract(self):
        with pytest.raises(TypeError, match="abstract"):
            Hatcher()  # type: ignore[abstract]

    def test_concrete_spawner(self):
        class FakeSpawner(Spawner):
            def parse(self, files):
                return ParseResult(skills=[], memory=[], mcp_configs={})

        assert isinstance(FakeSpawner().parse({}), ParseResult)

    def test_concrete_hatcher(self):
        class FakeHatcher(Hatcher):
            def render(self, egg, output_dir):
                return RenderResult(files={"out.txt": "hello"})

        result = FakeHatcher().render(make_egg(), Path("/tmp"))
        assert "out.txt" in result.files

    def test_all_connectors_subclass_spawner(self):
        from pynydus.agents.letta.spawner import LettaSpawner
        from pynydus.agents.openclaw.spawner import OpenClawSpawner
        from pynydus.agents.zeroclaw.spawner import ZeroClawSpawner

        for cls in (OpenClawSpawner, LettaSpawner, ZeroClawSpawner):
            assert issubclass(cls, Spawner)

    def test_all_connectors_subclass_hatcher(self):
        from pynydus.agents.letta.hatcher import LettaHatcher
        from pynydus.agents.openclaw.hatcher import OpenClawHatcher
        from pynydus.agents.zeroclaw.hatcher import ZeroClawHatcher

        for cls in (OpenClawHatcher, LettaHatcher, ZeroClawHatcher):
            assert issubclass(cls, Hatcher)


# =====================================================================
# Egg artifact fields
# =====================================================================


class TestEggArtifactFields:
    def test_all_artifacts_together(self):
        egg = make_egg(
            a2a_card={"name": "X", "skills": []},
            agents_md="# AGENTS\n",
            apm_yml="name: x\n",
            spec_snapshots={"a.md": "content"},
        )
        assert egg.a2a_card["name"] == "X"
        assert "AGENTS" in egg.agents_md
        assert egg.apm_yml == "name: x\n"
        assert "a.md" in egg.spec_snapshots

    def test_neutral_manifest_fields_propagate(self):
        egg = make_egg(agent_name="Bot", llm_model="claude-sonnet-4-20250514")
        assert egg.manifest.agent_name == "Bot"
        assert egg.manifest.llm_model == "claude-sonnet-4-20250514"


# =====================================================================
# ModuleType / Bucket alias
# =====================================================================


class TestModuleTypeAlias:
    def test_bucket_is_module_type(self):
        assert Bucket is ModuleType

    def test_values(self):
        assert ModuleType.SKILL == "skill"
        assert ModuleType.MEMORY == "memory"
        assert ModuleType.SECRET == "secret"
