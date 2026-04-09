"""Tests for pipeline helpers and phases."""

from __future__ import annotations

from pathlib import Path

from pynydus.api.schemas import (
    MemoryModule,
    MemoryRecord,
    SecretsModule,
    SkillRecord,
    SkillsModule,
)
from pynydus.common.enums import AgentType, MemoryLabel
from pynydus.engine.nydusfile import SourceDirective
from pynydus.engine.pipeline import (
    PipelineContext,
    _apply_custom_labels,
    _package_egg,
)

# ---------------------------------------------------------------------------
# _apply_custom_labels
# ---------------------------------------------------------------------------


class TestApplyCustomLabels:
    def test_pattern_match(self):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="x",
                    label=MemoryLabel.STATE,
                    agent_type="x",
                    source_store="SOUL.md",
                ),
                MemoryRecord(
                    id="m2",
                    text="y",
                    label=MemoryLabel.STATE,
                    agent_type="x",
                    source_store="MEMORY.md",
                ),
            ]
        )
        _apply_custom_labels(
            memory,
            {
                "SOUL*": MemoryLabel.PERSONA.value,
                "MEMORY*": MemoryLabel.STATE.value,
            },
        )
        assert memory.memory[0].label == MemoryLabel.PERSONA
        assert memory.memory[1].label == MemoryLabel.STATE

    def test_no_match(self):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="x",
                    label=MemoryLabel.FLOW,
                    agent_type="x",
                    source_store="other.md",
                ),
            ]
        )
        _apply_custom_labels(memory, {"SOUL*": MemoryLabel.PERSONA.value})
        assert memory.memory[0].label == MemoryLabel.FLOW

    def test_first_match_wins(self):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="x",
                    label=MemoryLabel.STATE,
                    agent_type="x",
                    source_store="SOUL.md",
                ),
            ]
        )
        _apply_custom_labels(
            memory,
            {
                "SOUL*": MemoryLabel.PERSONA.value,
                "*.md": MemoryLabel.STATE.value,
            },
        )
        assert memory.memory[0].label == MemoryLabel.PERSONA

    def test_glob_pattern(self):
        memory = MemoryModule(
            memory=[
                MemoryRecord(
                    id="m1",
                    text="x",
                    label=MemoryLabel.PERSONA,
                    agent_type="x",
                    source_store="SOUL.md",
                ),
                MemoryRecord(
                    id="m2",
                    text="y",
                    label=MemoryLabel.STATE,
                    agent_type="x",
                    source_store="MEMORY.md",
                ),
                MemoryRecord(
                    id="m3",
                    text="z",
                    label=MemoryLabel.CONTEXT,
                    agent_type="x",
                    source_store="debug.log",
                ),
            ]
        )
        _apply_custom_labels(memory, {"*.md": MemoryLabel.CONTEXT.value})
        md_records = [r for r in memory.memory if r.source_store.endswith(".md")]
        assert all(r.label == MemoryLabel.CONTEXT for r in md_records)
        assert memory.memory[2].label == MemoryLabel.CONTEXT  # unchanged


# ---------------------------------------------------------------------------
# _package_egg
# ---------------------------------------------------------------------------


class TestPhase8Package:
    def test_basic_packaging(self):
        ctx = PipelineContext(
            nydusfile_dir=Path("/tmp/test"),
            agent_type=AgentType.OPENCLAW,
        )
        skills = SkillsModule(
            skills=[SkillRecord(id="s1", name="greet", agent_type="x", content="hi")]
        )
        memory = MemoryModule()
        secrets = SecretsModule()

        egg = _package_egg(ctx, skills, memory, secrets, {"k": "v"})
        assert egg.manifest.agent_type == AgentType.OPENCLAW
        assert len(egg.skills.skills) == 1
        assert egg.manifest.source_metadata == {"k": "v"}

    def test_sources_in_manifest(self):
        ctx = PipelineContext(
            nydusfile_dir=Path("/tmp/test"),
            sources=[
                SourceDirective(agent_type="openclaw", path="/a"),
            ],
            agent_type=AgentType.OPENCLAW,
        )
        egg = _package_egg(
            ctx,
            SkillsModule(),
            MemoryModule(),
            SecretsModule(),
            {},
        )
        assert len(egg.manifest.sources) == 1
        assert egg.manifest.sources[0].agent_type == "openclaw"
        assert egg.manifest.sources[0].source_path == "/a"


# ---------------------------------------------------------------------------
# PipelineContext
# ---------------------------------------------------------------------------


class TestPipelineContext:
    def test_custom_values(self):
        ctx = PipelineContext(
            nydusfile_dir=Path("/tmp"),
            agent_type=AgentType.LETTA,
            redact=False,
        )
        assert ctx.agent_type == AgentType.LETTA
        assert ctx.redact is False
