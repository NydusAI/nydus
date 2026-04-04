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
        "soul.md": "I am a research assistant.\n\nI prefer concise answers.",
        "knowledge.md": "# Physics\n\nSpeed of light is 299792458 m/s.",
        "skill.md": "# Summarize\n\nProduce a summary.\n\n# Translate\n\nTranslate text.",
        "AGENTS.md": "Follow structured output format.",
        "USER.md": "User prefers Python.",
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
                source_store="soul.md",
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
                source_store="knowledge.md",
            ),
        ],
    )


class TestOpenClawParse:
    def test_skill_headings(self, spawner, oc_files):
        result = spawner.parse(oc_files)
        names = [s.name for s in result.skills]
        assert "Summarize" in names
        assert "Translate" in names

    def test_skills_dir(self, spawner, oc_files):
        result = spawner.parse(oc_files)
        assert any(s.source_file == "skills/greet.md" for s in result.skills)

    def test_soul_persona(self, spawner, oc_files):
        result = spawner.parse(oc_files)
        persona = [m for m in result.memory if m.label == MemoryLabel.PERSONA]
        assert any(m.source_file == "soul.md" for m in persona)

    def test_knowledge_state(self, spawner, oc_files):
        result = spawner.parse(oc_files)
        state = [m for m in result.memory if m.label == MemoryLabel.STATE]
        assert any(m.source_file == "knowledge.md" for m in state)

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
        files = {"soul.md": "   \n\n   "}
        result = spawner.parse(files)
        assert len(result.memory) == 0


class TestOpenClawRender:
    def test_filenames(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        assert "soul.md" in result.files
        assert "skill.md" in result.files
        assert "knowledge.md" in result.files
        assert "agents.md" in result.files
        assert "user.md" in result.files

    def test_skill_sections(self, hatcher):
        egg = _rich_egg()
        result = hatcher.render(egg)
        assert "# greet" in result.files["skill.md"]

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
