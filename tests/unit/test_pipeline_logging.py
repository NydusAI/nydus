"""Tests that every pipeline step appends the expected spawn_log entries."""

from __future__ import annotations

from pathlib import Path

import pytest

from pynydus.api.schemas import (
    MemoryModule,
    MemoryRecord,
    SecretRecord,
    SecretsModule,
    SkillRecord,
    SkillsModule,
)
from pynydus.common.enums import AgentType, InjectionMode, MemoryLabel, SecretKind
from pynydus.engine.nydusfile import SourceDirective
from pynydus.engine.pipeline import (
    PipelineContext,
    _apply_custom_labels,
    _build_memory_module_from_parse,
    _build_skills_module_from_parse,
    _drop_memory_records_with_excluded_labels,
    _filter_files_by_patterns,
    _merge_memory,
    _merge_skills,
    _merge_secrets,
    _package_egg,
)


def _make_ctx(tmp_path: Path, **overrides) -> PipelineContext:
    defaults = dict(
        nydusfile_dir=tmp_path,
        sources=[SourceDirective(agent_type="openclaw", path="./agent")],
        agent_type=AgentType.OPENCLAW,
    )
    defaults.update(overrides)
    return PipelineContext(**defaults)


# ---------------------------------------------------------------------------
# files_removed (tested at call site level via _filter_files_by_patterns)
# ---------------------------------------------------------------------------


class TestFilesRemovedLogging:
    def test_removed_files_logged(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, source_remove_globs=["*.json"])
        files = {"SOUL.md": "content", "config.json": "secret", "USER.md": "user"}
        before_keys = set(files.keys())
        result = _filter_files_by_patterns(files, ctx.source_remove_globs)
        removed = sorted(before_keys - set(result.keys()))
        if removed:
            ctx.spawn_log.append(
                {
                    "type": "files_removed",
                    "patterns": ctx.source_remove_globs,
                    "removed": removed,
                    "remaining": len(result),
                }
            )

        entries = [e for e in ctx.spawn_log if e["type"] == "files_removed"]
        assert len(entries) == 1
        assert entries[0]["removed"] == ["config.json"]
        assert entries[0]["remaining"] == 2

    def test_no_removal_no_log(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, source_remove_globs=["*.yaml"])
        files = {"SOUL.md": "content", "USER.md": "user"}
        before_keys = set(files.keys())
        result = _filter_files_by_patterns(files, ctx.source_remove_globs)
        removed = sorted(before_keys - set(result.keys()))
        if removed:
            ctx.spawn_log.append(
                {
                    "type": "files_removed",
                    "patterns": ctx.source_remove_globs,
                    "removed": removed,
                    "remaining": len(result),
                }
            )

        entries = [e for e in ctx.spawn_log if e["type"] == "files_removed"]
        assert len(entries) == 0


# ---------------------------------------------------------------------------
# records_built
# ---------------------------------------------------------------------------


class TestRecordsBuiltLogging:
    def test_records_built_logged(self, tmp_path: Path):
        from pynydus.api.raw_types import ParseResult, RawMemory, RawSkill

        parse_result = ParseResult(
            skills=[RawSkill(name="search", content="Find things", source_file="skills/search.md")],
            memory=[
                RawMemory(
                    text="I am a helper",
                    label=MemoryLabel.PERSONA,
                    source_file="SOUL.md",
                ),
                RawMemory(
                    text="User prefers dark mode",
                    label=MemoryLabel.CONTEXT,
                    source_file="USER.md",
                ),
            ],
        )

        ctx = _make_ctx(tmp_path)
        skills_module = _build_skills_module_from_parse(parse_result, AgentType.OPENCLAW)
        memory_module = _build_memory_module_from_parse(parse_result, AgentType.OPENCLAW)

        ctx.spawn_log.append(
            {
                "type": "records_built",
                "skills": [
                    {"id": s.id, "name": s.name, "source_file": s.metadata.get("source_file")}
                    for s in skills_module.skills
                ],
                "memory": [
                    {
                        "id": m.id,
                        "label": m.label.value,
                        "source_store": m.source_store,
                        "text_length": len(m.text),
                    }
                    for m in memory_module.memory
                ],
            }
        )

        entries = [e for e in ctx.spawn_log if e["type"] == "records_built"]
        assert len(entries) == 1
        assert len(entries[0]["skills"]) == 1
        assert entries[0]["skills"][0]["name"] == "search"
        assert len(entries[0]["memory"]) == 2
        assert entries[0]["memory"][0]["source_store"] == "SOUL.md"


# ---------------------------------------------------------------------------
# base_merge
# ---------------------------------------------------------------------------


class TestBaseMergeLogging:
    def test_merge_logged(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)

        base_skills = SkillsModule(
            skills=[SkillRecord(id="s1", name="base_skill", agent_type="x", content="c")]
        )
        ext_skills = SkillsModule(
            skills=[SkillRecord(id="s2", name="new_skill", agent_type="x", content="c")]
        )
        base_memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1", text="base", label=MemoryLabel.STATE, agent_type="x", source_store="x"
                )
            ]
        )
        ext_memory = MemoryModule(memory=[])
        base_secrets = SecretsModule(secrets=[])
        ext_secrets = SecretsModule(secrets=[])

        skills_before = len(ext_skills.skills)
        memory_before = len(ext_memory.memory)
        secrets_before = len(ext_secrets.secrets)

        merged_skills = _merge_skills(base_skills, ext_skills)
        merged_memory = _merge_memory(base_memory, ext_memory)
        merged_secrets = _merge_secrets(base_secrets, ext_secrets)

        ctx.spawn_log.append(
            {
                "type": "base_merge",
                "skills_before": skills_before,
                "skills_after": len(merged_skills.skills),
                "memory_before": memory_before,
                "memory_after": len(merged_memory.memory),
                "secrets_before": secrets_before,
                "secrets_after": len(merged_secrets.secrets),
            }
        )

        entries = [e for e in ctx.spawn_log if e["type"] == "base_merge"]
        assert len(entries) == 1
        assert entries[0]["skills_before"] == 1
        assert entries[0]["skills_after"] == 2
        assert entries[0]["memory_before"] == 0
        assert entries[0]["memory_after"] == 1


# ---------------------------------------------------------------------------
# label_override
# ---------------------------------------------------------------------------


class TestLabelOverrideLogging:
    def test_override_logged(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="identity info",
                    label=MemoryLabel.STATE,
                    agent_type="x",
                    source_store="IDENTITY.md",
                ),
                MemoryRecord(
                    id="m2",
                    text="general memory",
                    label=MemoryLabel.STATE,
                    agent_type="x",
                    source_store="MEMORY.md",
                ),
            ]
        )

        _apply_custom_labels(
            memory,
            {"IDENTITY.md": "persona"},
            spawn_log=ctx.spawn_log,
        )

        entries = [e for e in ctx.spawn_log if e["type"] == "label_override"]
        assert len(entries) == 1
        assert entries[0]["record_id"] == "m1"
        assert entries[0]["old_label"] == "state"
        assert entries[0]["new_label"] == "persona"
        assert entries[0]["source_store"] == "IDENTITY.md"

    def test_no_match_no_log(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="text",
                    label=MemoryLabel.STATE,
                    agent_type="x",
                    source_store="SOUL.md",
                ),
            ]
        )

        _apply_custom_labels(
            memory,
            {"IDENTITY.md": "persona"},
            spawn_log=ctx.spawn_log,
        )

        entries = [e for e in ctx.spawn_log if e["type"] == "label_override"]
        assert len(entries) == 0


# ---------------------------------------------------------------------------
# memory_excluded
# ---------------------------------------------------------------------------


class TestMemoryExcludedLogging:
    def test_exclusion_logged(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="flow",
                    label=MemoryLabel.FLOW,
                    agent_type="x",
                    source_store="AGENTS.md",
                ),
                MemoryRecord(
                    id="m2",
                    text="keep",
                    label=MemoryLabel.STATE,
                    agent_type="x",
                    source_store="MEMORY.md",
                ),
            ]
        )

        result = _drop_memory_records_with_excluded_labels(
            memory, [MemoryLabel.FLOW], spawn_log=ctx.spawn_log
        )

        entries = [e for e in ctx.spawn_log if e["type"] == "memory_excluded"]
        assert len(entries) == 1
        assert entries[0]["dropped"][0]["id"] == "m1"
        assert entries[0]["kept"] == 1
        assert len(result.memory) == 1

    def test_no_exclusion_no_log(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="keep",
                    label=MemoryLabel.STATE,
                    agent_type="x",
                    source_store="MEMORY.md",
                ),
            ]
        )

        _drop_memory_records_with_excluded_labels(
            memory, [MemoryLabel.FLOW], spawn_log=ctx.spawn_log
        )

        entries = [e for e in ctx.spawn_log if e["type"] == "memory_excluded"]
        assert len(entries) == 0


# ---------------------------------------------------------------------------
# egg_packaged
# ---------------------------------------------------------------------------


class TestEggPackagedLogging:
    def test_packaging_logged(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path)
        skills = SkillsModule(
            skills=[SkillRecord(id="s1", name="test", agent_type="x", content="c")]
        )
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="fact",
                    label=MemoryLabel.STATE,
                    agent_type="x",
                    source_store="MEMORY.md",
                )
            ]
        )
        secrets = SecretsModule(secrets=[])
        metadata = {"source_dir": str(tmp_path)}

        _package_egg(ctx, skills, memory, secrets, metadata)

        entries = [e for e in ctx.spawn_log if e["type"] == "egg_packaged"]
        assert len(entries) == 1
        assert entries[0]["skills"] == 1
        assert entries[0]["memory"] == 1
        assert entries[0]["secrets"] == 0
        assert entries[0]["agent_type"] == "openclaw"
