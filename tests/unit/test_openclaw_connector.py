"""Contract tests for OpenClaw spawner and hatcher."""

from __future__ import annotations

import pytest
from pynydus.agents.openclaw.hatcher import OpenClawHatcher
from pynydus.agents.openclaw.spawner import OpenClawSpawner
from pynydus.api.errors import HatchError
from pynydus.api.schemas import MemoryRecord, SkillRecord
from pynydus.common.enums import MemoryLabel

from conftest import make_egg


@pytest.fixture
def spawner():
    return OpenClawSpawner()


@pytest.fixture
def hatcher():
    return OpenClawHatcher()


@pytest.fixture
def oc_files():
    return {
        "SOUL.md": "I am a research assistant.\n\nI prefer concise answers.",
        "MEMORY.md": "# Physics\n\nSpeed of light is 299792458 m/s.",
        "AGENTS.md": "Follow structured output format.",
        "USER.md": "User prefers Python.",
        "skills/summarize.md": "Produce a summary.",
        "skills/translate.md": "Translate text.",
        "skills/greet.md": "Say hello to the user.",
        "memory/2026-01-15.md": "Had a productive session.",
    }


def _rich_egg():
    return make_egg(
        skills=[SkillRecord(id="s1", name="greet", agent_type="openclaw", content="Say hello.")],
        memory=[
            MemoryRecord(
                id="m1",
                text="I am helpful.",
                label=MemoryLabel.PERSONA,
                agent_type="openclaw",
                source_store="SOUL.md",
            ),
            MemoryRecord(
                id="m2",
                text="Follow rules.",
                label=MemoryLabel.FLOW,
                agent_type="openclaw",
                source_store="AGENTS.md",
            ),
            MemoryRecord(
                id="m3",
                text="User likes code.",
                label=MemoryLabel.CONTEXT,
                agent_type="openclaw",
                source_store="USER.md",
            ),
            MemoryRecord(
                id="m4",
                text="Python is great.",
                label=MemoryLabel.STATE,
                agent_type="openclaw",
                source_store="MEMORY.md",
            ),
        ],
    )


def _rich_egg_with_splits():
    """Egg with IDENTITY, TOOLS, dated memory — tests file-splitting logic."""
    from datetime import datetime, timezone

    return make_egg(
        skills=[
            SkillRecord(id="s1", name="greet", agent_type="openclaw", content="Say hello."),
            SkillRecord(
                id="s2", name="search hotels", agent_type="openclaw", content="Find hotels."
            ),
        ],
        memory=[
            MemoryRecord(
                id="m1",
                text="I am helpful.",
                label=MemoryLabel.PERSONA,
                agent_type="openclaw",
                source_store="SOUL.md",
            ),
            MemoryRecord(
                id="m2",
                text="Atlas 🏔️",
                label=MemoryLabel.PERSONA,
                agent_type="openclaw",
                source_store="IDENTITY.md",
            ),
            MemoryRecord(
                id="m3",
                text="Follow rules.",
                label=MemoryLabel.FLOW,
                agent_type="openclaw",
                source_store="AGENTS.md",
            ),
            MemoryRecord(
                id="m4",
                text="User likes code.",
                label=MemoryLabel.CONTEXT,
                agent_type="openclaw",
                source_store="USER.md",
            ),
            MemoryRecord(
                id="m5",
                text="API endpoint: https://api.example.com",
                label=MemoryLabel.CONTEXT,
                agent_type="openclaw",
                source_store="TOOLS.md",
            ),
            MemoryRecord(
                id="m6",
                text="Curated long-term note.",
                label=MemoryLabel.STATE,
                agent_type="openclaw",
                source_store="MEMORY.md",
            ),
            MemoryRecord(
                id="m7",
                text="Had a productive session.",
                label=MemoryLabel.STATE,
                agent_type="openclaw",
                source_store="memory/2026-01-15.md",
                timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc),
            ),
            MemoryRecord(
                id="m8",
                text="Follow-up session.",
                label=MemoryLabel.STATE,
                agent_type="openclaw",
                source_store="memory/2026-01-16.md",
                timestamp=datetime(2026, 1, 16, tzinfo=timezone.utc),
            ),
        ],
    )


def _cross_platform_egg():
    """Egg from a non-OpenClaw source (e.g. Letta) — no OpenClaw source_store hints."""
    return make_egg(
        skills=[SkillRecord(id="s1", name="analyze", agent_type="letta", content="Analyze data.")],
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


class TestOpenClawParse:
    def test_skill_headings(self, spawner, oc_files):
        result = spawner.parse(oc_files)
        names = [s.name for s in result.skills]
        assert "summarize" in names
        assert "translate" in names

    def test_skills_dir(self, spawner, oc_files):
        result = spawner.parse(oc_files)
        assert any(s.source_file == "skills/greet.md" for s in result.skills)

    def test_soul_persona(self, spawner, oc_files):
        result = spawner.parse(oc_files)
        persona = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert any(m.source_file == "SOUL.md" for m in persona)

    def test_knowledge_state(self, spawner, oc_files):
        result = spawner.parse(oc_files)
        state = [m for m in result.memory if m.label == MemoryLabel.STATE]
        assert any(m.source_file == "MEMORY.md" for m in state)

    def test_agents_flow(self, spawner, oc_files):
        result = spawner.parse(oc_files)
        flow = [m for m in result.memory if m.label == MemoryLabel.FLOW]
        assert any(m.source_file == "AGENTS.md" for m in flow)

    def test_user_context(self, spawner, oc_files):
        result = spawner.parse(oc_files)
        ctx = [m for m in result.memory if m.label == MemoryLabel.CONTEXT]
        assert any(m.source_file == "USER.md" for m in ctx)

    def test_dated_memory(self, spawner, oc_files):
        result = spawner.parse(oc_files)
        dated = [m for m in result.memory if m.source_file == "memory/2026-01-15.md"]
        assert dated[0].timestamp is not None

    def test_empty(self, spawner):
        result = spawner.parse({})
        assert len(result.skills) == 0
        assert len(result.memory) == 0

    def test_empty_skill_md(self, spawner):
        files = {"skill.md": "   \n\n   \n"}
        result = spawner.parse(files)
        assert len(result.skills) == 0

    def test_nested_headings(self, spawner):
        files = {"skill.md": "# Main\n\nIntro.\n\n## Sub\n\nDetail."}
        result = spawner.parse(files)
        names = [s.name for s in result.skills]
        assert "Main" in names

    def test_mcp_malformed_json(self, spawner):
        files = {"mcp.json": "NOT VALID JSON{{{"}
        result = spawner.parse(files)
        assert result.mcp_configs == {}

    def test_whitespace_only_memory(self, spawner):
        files = {"SOUL.md": "   \n\n   "}
        result = spawner.parse(files)
        assert len(result.memory) == 0


class TestOpenClawRender:
    def test_canonical_filenames(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        assert "SOUL.md" in result.files
        assert "AGENTS.md" in result.files
        assert "USER.md" in result.files
        assert "MEMORY.md" in result.files
        assert "skills/greet.md" in result.files
        assert "soul.md" not in result.files
        assert "agents.md" not in result.files
        assert "user.md" not in result.files
        assert "knowledge.md" not in result.files
        assert "skill.md" not in result.files

    def test_skill_per_file(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        assert "Say hello." in result.files["skills/greet.md"]

    def test_multiple_skills_separate_files(self, hatcher):
        egg = _rich_egg_with_splits()
        result = hatcher.render(egg)
        assert "skills/greet.md" in result.files
        assert "skills/search-hotels.md" in result.files

    def test_identity_split(self, hatcher):
        egg = _rich_egg_with_splits()
        result = hatcher.render(egg)
        assert "SOUL.md" in result.files
        assert "IDENTITY.md" in result.files
        assert "Atlas" in result.files["IDENTITY.md"]
        assert "I am helpful." in result.files["SOUL.md"]

    def test_tools_split(self, hatcher):
        egg = _rich_egg_with_splits()
        result = hatcher.render(egg)
        assert "USER.md" in result.files
        assert "TOOLS.md" in result.files
        assert "api.example.com" in result.files["TOOLS.md"]
        assert "User likes code." in result.files["USER.md"]

    def test_dated_memory(self, hatcher):
        egg = _rich_egg_with_splits()
        result = hatcher.render(egg)
        assert "MEMORY.md" in result.files
        assert "memory/2026-01-15.md" in result.files
        assert "memory/2026-01-16.md" in result.files
        assert "productive session" in result.files["memory/2026-01-15.md"]
        assert "Curated long-term note." in result.files["MEMORY.md"]

    def test_cross_platform_fallback(self, hatcher):
        egg = _cross_platform_egg()
        result = hatcher.render(egg)
        assert "SOUL.md" in result.files
        assert "AGENTS.md" in result.files
        assert "USER.md" in result.files
        assert "MEMORY.md" in result.files
        assert "skills/analyze.md" in result.files
        assert "IDENTITY.md" not in result.files
        assert "TOOLS.md" not in result.files

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
        assert "{{SECRET_001}}" in result.files["config.json"]

    def test_empty_raises(self, hatcher):
        egg = make_egg(skills=[], memory=[])
        with pytest.raises(HatchError):
            hatcher.render(egg)
