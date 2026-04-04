"""Tests for the Egg diff engine (engine/differ.py)."""

from __future__ import annotations

from datetime import UTC, datetime

from pynydus.api.schemas import (
    Egg,
    Manifest,
    MemoryModule,
    MemoryRecord,
    SecretRecord,
    SecretsModule,
    SkillRecord,
    SkillsModule,
)
from pynydus.common.enums import (
    AgentType,
    Bucket,
    DiffChange,
    MemoryLabel,
    SecretKind,
)
from pynydus.engine.differ import diff_eggs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_egg(
    *,
    agent_type: AgentType = AgentType.OPENCLAW,
    skills: list[SkillRecord] | None = None,
    memory: list[MemoryRecord] | None = None,
    secrets: list[SecretRecord] | None = None,
) -> Egg:
    return Egg(
        manifest=Manifest(
            nydus_version="0.1.0",
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            agent_type=agent_type,
            included_modules=[Bucket.SKILL, Bucket.MEMORY, Bucket.SECRET],
        ),
        skills=SkillsModule(skills=skills or []),
        memory=MemoryModule(memory=memory or []),
        secrets=SecretsModule(secrets=secrets or []),
    )


def _skill(id: str, name: str = "skill", content: str = "content") -> SkillRecord:
    return SkillRecord(
        id=id,
        name=name,
        agent_type="markdown_skill",
        content=content,
    )


def _memory(id: str, text: str = "fact", label: MemoryLabel = MemoryLabel.STATE) -> MemoryRecord:
    return MemoryRecord(
        id=id,
        text=text,
        label=label,
        agent_type="openclaw",
        source_store="knowledge.md",
    )


def _secret(id: str, name: str = "API_KEY") -> SecretRecord:
    return SecretRecord(
        id=id,
        placeholder=f"{{{{{id}}}}}",
        kind=SecretKind.CREDENTIAL,
        name=name,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIdentical:
    def test_identical_eggs(self):
        egg = _make_egg(
            skills=[_skill("s1")],
            memory=[_memory("m1")],
            secrets=[_secret("sec1")],
        )
        report = diff_eggs(egg, egg)
        assert report.identical
        assert report.entries == []

    def test_empty_eggs(self):
        report = diff_eggs(_make_egg(), _make_egg())
        assert report.identical


class TestSkillDiff:
    def test_skill_added(self):
        a = _make_egg(skills=[_skill("s1")])
        b = _make_egg(skills=[_skill("s1"), _skill("s2", name="New Skill")])

        report = diff_eggs(a, b)

        assert not report.identical
        added = [e for e in report.entries if e.change == DiffChange.ADDED]
        assert len(added) == 1
        assert added[0].bucket == Bucket.SKILL
        assert added[0].id == "s2"

    def test_skill_removed(self):
        a = _make_egg(skills=[_skill("s1"), _skill("s2")])
        b = _make_egg(skills=[_skill("s1")])

        report = diff_eggs(a, b)

        removed = [e for e in report.entries if e.change == DiffChange.REMOVED]
        assert len(removed) == 1
        assert removed[0].id == "s2"

    def test_skill_modified(self):
        a = _make_egg(skills=[_skill("s1", name="Old Name", content="old")])
        b = _make_egg(skills=[_skill("s1", name="New Name", content="new")])

        report = diff_eggs(a, b)

        modified = [e for e in report.entries if e.change == DiffChange.MODIFIED]
        assert len(modified) == 2  # name + content
        fields = {e.field for e in modified}
        assert fields == {"name", "content"}

    def test_skill_unchanged_not_reported(self):
        s = _skill("s1", name="Same", content="Same")
        report = diff_eggs(_make_egg(skills=[s]), _make_egg(skills=[s]))
        skill_entries = [e for e in report.entries if e.bucket == Bucket.SKILL]
        assert skill_entries == []


class TestMemoryDiff:
    def test_memory_added_removed(self):
        a = _make_egg(memory=[_memory("m1"), _memory("m2")])
        b = _make_egg(memory=[_memory("m1"), _memory("m3", text="new fact")])

        report = diff_eggs(a, b)

        removed = [
            e
            for e in report.entries
            if e.change == DiffChange.REMOVED and e.bucket == Bucket.MEMORY
        ]
        added = [
            e for e in report.entries if e.change == DiffChange.ADDED and e.bucket == Bucket.MEMORY
        ]
        assert len(removed) == 1
        assert removed[0].id == "m2"
        assert len(added) == 1
        assert added[0].id == "m3"

    def test_memory_modified(self):
        a = _make_egg(memory=[_memory("m1", text="old text", label=MemoryLabel.STATE)])
        b = _make_egg(memory=[_memory("m1", text="new text", label=MemoryLabel.PERSONA)])

        report = diff_eggs(a, b)

        modified = [e for e in report.entries if e.change == DiffChange.MODIFIED]
        assert len(modified) == 2  # text + label
        fields = {e.field for e in modified}
        assert fields == {"text", "label"}


class TestSecretDiff:
    def test_secret_added(self):
        a = _make_egg(secrets=[_secret("sec1")])
        b = _make_egg(secrets=[_secret("sec1"), _secret("sec2", name="DB_PASS")])

        report = diff_eggs(a, b)

        added = [
            e for e in report.entries if e.change == DiffChange.ADDED and e.bucket == Bucket.SECRET
        ]
        assert len(added) == 1
        assert added[0].id == "sec2"

    def test_secret_removed(self):
        a = _make_egg(secrets=[_secret("sec1"), _secret("sec2")])
        b = _make_egg(secrets=[_secret("sec1")])

        report = diff_eggs(a, b)

        removed = [
            e
            for e in report.entries
            if e.change == DiffChange.REMOVED and e.bucket == Bucket.SECRET
        ]
        assert len(removed) == 1
        assert removed[0].id == "sec2"

    def test_secret_modified(self):
        s1 = SecretRecord(
            id="sec1", placeholder="{{OLD}}", kind=SecretKind.CREDENTIAL, name="OLD_KEY"
        )
        s2 = SecretRecord(
            id="sec1", placeholder="{{NEW}}", kind=SecretKind.CREDENTIAL, name="NEW_KEY"
        )
        report = diff_eggs(_make_egg(secrets=[s1]), _make_egg(secrets=[s2]))

        modified = [e for e in report.entries if e.change == DiffChange.MODIFIED]
        fields = {e.field for e in modified}
        assert "placeholder" in fields
        assert "name" in fields


class TestManifestDiff:
    def test_different_agent_type(self):
        a = _make_egg(agent_type=AgentType.OPENCLAW)
        b = _make_egg(agent_type=AgentType.LETTA)

        report = diff_eggs(a, b)

        fields = {mc.field for mc in report.manifest_changes}
        assert "agent_type" in fields


class TestMultipleChanges:
    def test_skills_memory_manifest_all_differ(self):
        a = _make_egg(
            agent_type=AgentType.OPENCLAW,
            skills=[_skill("s1", name="Old")],
            memory=[_memory("m1", text="old fact")],
        )
        b = _make_egg(
            agent_type=AgentType.LETTA,
            skills=[_skill("s1", name="New"), _skill("s2")],
            memory=[_memory("m1", text="new fact")],
        )

        report = diff_eggs(a, b)

        assert not report.identical
        assert len(report.manifest_changes) > 0
        buckets = {e.bucket for e in report.entries}
        assert Bucket.SKILL in buckets
        assert Bucket.MEMORY in buckets
