"""Shared test fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pynydus.api.schemas import (
    Egg,
    HatchResult,
    Manifest,
    MemoryModule,
    MemoryRecord,
    SkillRecord,
    SkillsModule,
)
from pynydus.common.enums import AgentType, Bucket, MemoryLabel
from pynydus.llm import LLMTierConfig

# ---------------------------------------------------------------------------
# Hatch-to-disk helper (shared by hatcher tests)
# ---------------------------------------------------------------------------


def _hatch_to_disk(hatcher, egg: Egg, output_dir: Path) -> HatchResult:
    """Render an Egg via *hatcher* and write the files to *output_dir*.

    Returns a :class:`HatchResult` with the created file list.
    """
    result = hatcher.render(egg)

    output_dir.mkdir(parents=True, exist_ok=True)
    files_created: list[str] = []
    for fname, content in result.files.items():
        fpath = output_dir / fname
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content)
        files_created.append(fname)

    return HatchResult(
        target=egg.manifest.agent_type,
        output_dir=output_dir,
        files_created=files_created,
        warnings=list(result.warnings),
    )


@pytest.fixture
def hatch_to_disk():
    """Fixture providing a render-and-write helper for per-agent hatcher tests."""
    return _hatch_to_disk


# ---------------------------------------------------------------------------
# Egg factory
# ---------------------------------------------------------------------------


def make_egg(
    *,
    agent_type: AgentType = AgentType.OPENCLAW,
    included_modules: list[str] | None = None,
    skills: list[SkillRecord] | None = None,
    memory: list[MemoryRecord] | None = None,
    nydus_version: str = "0.1.0",
    **manifest_kw,
) -> Egg:
    """Build an :class:`Egg` with sensible defaults.

    Pass ``skills`` / ``memory`` to override the default single-record modules.
    Extra *manifest_kw* are forwarded to :class:`Manifest`.
    """
    if included_modules is None:
        included_modules = [Bucket.SKILL, Bucket.MEMORY]

    if skills is None:
        skills = [
            SkillRecord(
                id="skill_001",
                name="test",
                agent_type="markdown_skill",
                content="Test skill.",
            )
        ]

    if memory is None:
        memory = [
            MemoryRecord(
                id="mem_001",
                text="A fact.",
                label=MemoryLabel.STATE,
                agent_type="openclaw",
                source_store="knowledge.md",
            )
        ]

    manifest_kw.setdefault("created_at", datetime.now(UTC))

    return Egg(
        manifest=Manifest(
            nydus_version=nydus_version,
            agent_type=agent_type,
            included_modules=included_modules,
            **manifest_kw,
        ),
        skills=SkillsModule(skills=skills),
        memory=MemoryModule(memory=memory),
    )


# ---------------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _wide_terminal(monkeypatch):
    monkeypatch.setenv("COLUMNS", "200")


@pytest.fixture
def sample_egg() -> Egg:
    """A basic Egg with 1 skill, 1 memory record — the most common test shape."""
    return make_egg()


@pytest.fixture
def minimal_egg() -> Egg:
    """An Egg with only a manifest and empty modules."""
    return make_egg(skills=[], memory=[], included_modules=[Bucket.SKILL, Bucket.MEMORY])


@pytest.fixture
def openclaw_project(tmp_path: Path) -> Path:
    """Create a minimal OpenClaw project directory."""
    (tmp_path / "soul.md").write_text(
        "I am a research assistant.\n\nI prefer concise summaries.\n\nContact: alex@example.com\n"
    )
    (tmp_path / "knowledge.md").write_text(
        "# Domain Knowledge\n\n"
        "The speed of light is 299,792,458 m/s.\n\n"
        "Python 3.12 was released in October 2023.\n"
    )
    (tmp_path / "skill.md").write_text(
        "# Summarize Documents\n\n"
        "Produce a 5-bullet summary of any document.\n\n"
        "# Data Analysis\n\n"
        "Process CSV data and generate statistical summaries.\n"
    )
    (tmp_path / "config.json").write_text(
        '{"aws_access_key_id": "AKIAYRWSSQ3BPTB4DX7Z", "model": "gpt-4"}\n'
    )
    return tmp_path


@pytest.fixture
def llm_config() -> LLMTierConfig:
    """LLM tier for tests that need refinement."""
    return LLMTierConfig(
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        api_key="sk-ant-test",
    )
