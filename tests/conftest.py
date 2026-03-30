"""Shared test fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pynydus.api.schemas import (
    Egg,
    Manifest,
    MemoryLabel,
    MemoryModule,
    MemoryRecord,
    SkillRecord,
    SkillsModule,
    SourceType,
)
from pynydus.pkg.llm import LLMTierConfig, NydusLLMConfig


# ---------------------------------------------------------------------------
# Egg factory
# ---------------------------------------------------------------------------


def make_egg(
    *,
    source_type: SourceType = SourceType.OPENCLAW,
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
        included_modules = ["skills", "memory"]

    if skills is None:
        skills = [
            SkillRecord(
                id="skill_001",
                name="test",
                source_type="markdown_skill",
                content="Test skill.",
            )
        ]

    if memory is None:
        memory = [
            MemoryRecord(
                id="mem_001",
                text="A fact.",
                label=MemoryLabel.STATE,
                source_framework="openclaw",
                source_store="knowledge.md",
            )
        ]

    manifest_kw.setdefault("created_at", datetime.now(UTC))

    return Egg(
        manifest=Manifest(
            nydus_version=nydus_version,
            source_type=source_type,
            included_modules=included_modules,
            **manifest_kw,
        ),
        skills=SkillsModule(skills=skills),
        memory=MemoryModule(memory=memory),
    )


# ---------------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_egg() -> Egg:
    """A basic Egg with 1 skill, 1 memory record — the most common test shape."""
    return make_egg()


@pytest.fixture
def minimal_egg() -> Egg:
    """An Egg with only a manifest and empty modules."""
    return make_egg(skills=[], memory=[], included_modules=["skills", "memory"])


@pytest.fixture
def openclaw_project(tmp_path: Path) -> Path:
    """Create a minimal OpenClaw project directory."""
    (tmp_path / "soul.md").write_text(
        "I am a research assistant.\n\n"
        "I prefer concise summaries.\n\n"
        "Contact: alex@example.com\n"
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
        '{"api_key": "sk-secret-key-123", "model": "gpt-4"}\n'
    )
    return tmp_path


@pytest.fixture
def llm_config() -> NydusLLMConfig:
    """A two-tier LLM config for tests that need refinement."""
    return NydusLLMConfig(
        simple=LLMTierConfig(
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
            api_key="sk-ant-test",
        ),
        complex=LLMTierConfig(
            provider="openai",
            model="gpt-4o",
            api_key="sk-openai-test",
        ),
    )
