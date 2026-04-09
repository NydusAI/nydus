"""Tests for Agent Skills layout in .egg archives (v3: skills/ + nydus.json)."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from pynydus.api.schemas import (
    Egg,
    Manifest,
    MemoryModule,
    SecretsModule,
    SkillRecord,
    SkillsModule,
)
from pynydus.api.skill_format import parse_skill_md
from pynydus.common.enums import AgentType, Bucket
from pynydus.engine.packager import (
    load,
    read_logs,
    read_raw_artifacts,
    save,
    verify_egg_archive,
)


def _make_manifest(**overrides) -> Manifest:
    defaults = dict(
        nydus_version="0.5.0",
        created_at=datetime.now(UTC),
        agent_type=AgentType.OPENCLAW,
        included_modules=[Bucket.SKILL, Bucket.MEMORY, Bucket.SECRET],
    )
    defaults.update(overrides)
    return Manifest(**defaults)


def _make_egg(skills: list[SkillRecord] | None = None, **manifest_kw) -> Egg:
    return Egg(
        manifest=_make_manifest(**manifest_kw),
        skills=SkillsModule(skills=skills or []),
        memory=MemoryModule(),
        secrets=SecretsModule(),
    )


def _make_skill(name: str = "Greeting", content: str = "Say hello", **kw) -> SkillRecord:
    defaults = dict(
        id="skill_001",
        name=name,
        agent_type=AgentType.OPENCLAW,
        content=content,
    )
    defaults.update(kw)
    return SkillRecord(**defaults)


# ---------------------------------------------------------------------------
# Pack: skills written as SKILL.md directories
# ---------------------------------------------------------------------------


class TestPackSkillsFormat:
    def test_skill_written_as_skill_md(self, tmp_path: Path):
        egg = _make_egg(skills=[_make_skill()])
        egg_path = save(egg, tmp_path / "test")
        with zipfile.ZipFile(egg_path, "r") as zf:
            names = zf.namelist()
            # v3: skills/<slug>/SKILL.md
            skill_entries = [n for n in names if n.endswith("/SKILL.md")]
            assert len(skill_entries) == 1
            assert "skills/greeting/SKILL.md" in names

    def test_no_skills_json_written(self, tmp_path: Path):
        egg = _make_egg(skills=[_make_skill()])
        egg_path = save(egg, tmp_path / "test")
        with zipfile.ZipFile(egg_path, "r") as zf:
            assert "modules/skills.json" not in zf.namelist()

    def test_skill_md_content_parseable(self, tmp_path: Path):
        egg = _make_egg(skills=[_make_skill(name="Search", content="Search the web.")])
        egg_path = save(egg, tmp_path / "test")
        with zipfile.ZipFile(egg_path, "r") as zf:
            md = zf.read("skills/search/SKILL.md").decode()
        parsed = parse_skill_md(md)
        assert parsed.name == "Search"
        assert "Search the web" in parsed.body

    def test_multiple_skills_different_slugs(self, tmp_path: Path):
        skills = [
            _make_skill(id="skill_001", name="Greeting", content="Say hi"),
            _make_skill(id="skill_002", name="Search", content="Search web"),
        ]
        egg = _make_egg(skills=skills)
        egg_path = save(egg, tmp_path / "test")
        with zipfile.ZipFile(egg_path, "r") as zf:
            names = zf.namelist()
            skill_entries = [n for n in names if n.endswith("/SKILL.md")]
            assert len(skill_entries) == 2
            assert "skills/greeting/SKILL.md" in names
            assert "skills/search/SKILL.md" in names

    def test_duplicate_slugs_deduplicated(self, tmp_path: Path):
        skills = [
            _make_skill(id="skill_001", name="Greeting", content="v1"),
            _make_skill(id="skill_002", name="Greeting", content="v2"),
        ]
        egg = _make_egg(skills=skills)
        egg_path = save(egg, tmp_path / "test")
        with zipfile.ZipFile(egg_path, "r") as zf:
            skill_entries = [n for n in zf.namelist() if n.endswith("/SKILL.md")]
            assert len(skill_entries) == 2
            # One should be greeting, the other greeting-2 (skills/<slug>/SKILL.md)
            slugs = {n.split("/")[1] for n in skill_entries}
            assert "greeting" in slugs
            assert "greeting-2" in slugs

    def test_nydus_json_written(self, tmp_path: Path):
        egg = _make_egg(skills=[_make_skill(id="skill_042")])
        egg_path = save(egg, tmp_path / "test")
        with zipfile.ZipFile(egg_path, "r") as zf:
            assert "nydus.json" in zf.namelist()
            mapping = json.loads(zf.read("nydus.json"))
        assert "greeting" in mapping
        assert mapping["greeting"]["id"] == "skill_042"
        assert mapping["greeting"]["agent_type"] == "openclaw"

    def test_empty_skills(self, tmp_path: Path):
        egg = _make_egg(skills=[])
        egg_path = save(egg, tmp_path / "test")
        with zipfile.ZipFile(egg_path, "r") as zf:
            skill_entries = [n for n in zf.namelist() if "skills" in n]
            assert len(skill_entries) == 0

    def test_agent_type_in_frontmatter(self, tmp_path: Path):
        egg = _make_egg(skills=[_make_skill(agent_type=AgentType.LETTA)])
        egg_path = save(egg, tmp_path / "test")
        with zipfile.ZipFile(egg_path, "r") as zf:
            md = zf.read("skills/greeting/SKILL.md").decode()
        parsed = parse_skill_md(md)
        assert parsed.metadata.get("source_framework") == "letta"


class TestApmYmlPresence:
    def test_apm_yml_in_packed_archive(self, tmp_path: Path):
        egg = _make_egg(skills=[_make_skill()])
        egg_path = save(egg, tmp_path / "test")
        with zipfile.ZipFile(egg_path, "r") as zf:
            assert "apm.yml" in zf.namelist()


# ---------------------------------------------------------------------------
# Unpack: Agent Skills directories
# ---------------------------------------------------------------------------


class TestUnpackSkillsFormat:
    def test_round_trip_single_skill(self, tmp_path: Path):
        original = _make_egg(skills=[_make_skill(name="Greet", content="Say hello nicely")])
        egg_path = save(original, tmp_path / "test")
        loaded = load(egg_path)
        assert len(loaded.skills.skills) == 1
        assert loaded.skills.skills[0].name == "Greet"
        assert "Say hello nicely" in loaded.skills.skills[0].content

    def test_round_trip_multiple_skills(self, tmp_path: Path):
        skills = [
            _make_skill(id="skill_001", name="Greet", content="Say hi"),
            _make_skill(id="skill_002", name="Search", content="Search web"),
            _make_skill(id="skill_003", name="Translate", content="Translate text"),
        ]
        original = _make_egg(skills=skills)
        egg_path = save(original, tmp_path / "test")
        loaded = load(egg_path)
        assert len(loaded.skills.skills) == 3
        names = {s.name for s in loaded.skills.skills}
        assert names == {"Greet", "Search", "Translate"}

    def test_round_trip_preserves_ids(self, tmp_path: Path):
        skills = [
            _make_skill(id="skill_001", name="A", content="a"),
            _make_skill(id="skill_002", name="B", content="b"),
        ]
        original = _make_egg(skills=skills)
        egg_path = save(original, tmp_path / "test")
        loaded = load(egg_path)
        ids = {s.id for s in loaded.skills.skills}
        assert "skill_001" in ids
        assert "skill_002" in ids

    def test_round_trip_preserves_agent_type(self, tmp_path: Path):
        skill = _make_skill(agent_type=AgentType.LETTA)
        original = _make_egg(skills=[skill])
        egg_path = save(original, tmp_path / "test")
        loaded = load(egg_path)
        assert loaded.skills.skills[0].agent_type == "letta"

    def test_empty_skills_round_trip(self, tmp_path: Path):
        original = _make_egg(skills=[])
        egg_path = save(original, tmp_path / "test")
        loaded = load(egg_path)
        assert loaded.skills.skills == []


# ---------------------------------------------------------------------------
# save with raw artifacts
# ---------------------------------------------------------------------------


class TestPackWithRawSkills:
    def test_skills_as_skill_md(self, tmp_path: Path):
        egg = _make_egg(skills=[_make_skill()])
        egg_path = save(egg, tmp_path / "test", raw_artifacts={"SOUL.md": "hi"})
        with zipfile.ZipFile(egg_path, "r") as zf:
            names = zf.namelist()
            skill_entries = [n for n in names if n.endswith("/SKILL.md")]
            assert len(skill_entries) == 1
            assert "skills/greeting/SKILL.md" in names
            assert "modules/skills.json" not in names

    def test_raw_artifacts_preserved(self, tmp_path: Path):
        egg = _make_egg(skills=[_make_skill()])
        egg_path = save(egg, tmp_path / "test", raw_artifacts={"SOUL.md": "hi"})
        artifacts = read_raw_artifacts(egg_path)
        assert artifacts == {"SOUL.md": "hi"}

    def test_spawn_log_preserved(self, tmp_path: Path):
        egg = _make_egg()
        log = [{"type": "test", "msg": "hello"}]
        egg_path = save(egg, tmp_path / "test", spawn_log=log)
        with zipfile.ZipFile(egg_path, "r") as zf:
            names = zf.namelist()
            assert "spawn_log.json" in names
            assert not any(n.startswith("logs/") for n in names)
        logs = read_logs(egg_path)
        assert logs["spawn_log.json"] == log


# ---------------------------------------------------------------------------
# Signing with new format
# ---------------------------------------------------------------------------


class TestSigningWithSkillsMd:
    def test_signed_egg_verifies(self, tmp_path: Path):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key = Ed25519PrivateKey.generate()
        egg = _make_egg(skills=[_make_skill()])
        egg_path = save(egg, tmp_path / "test", private_key=key)
        assert verify_egg_archive(egg_path) is True

    def test_tampered_skill_fails_verification(self, tmp_path: Path):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key = Ed25519PrivateKey.generate()
        egg = _make_egg(skills=[_make_skill(content="original")])
        egg_path = save(egg, tmp_path / "test", private_key=key)

        # Tamper with the SKILL.md content
        tampered_path = tmp_path / "tampered.egg"
        with zipfile.ZipFile(egg_path, "r") as zf_in:
            with zipfile.ZipFile(tampered_path, "w") as zf_out:
                for name in zf_in.namelist():
                    data = zf_in.read(name)
                    if name.endswith("/SKILL.md"):
                        data = b"---\nname: TAMPERED\n---\n\ntampered content\n"
                    zf_out.writestr(name, data)

        assert verify_egg_archive(tampered_path) is False
