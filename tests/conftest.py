"""Shared test fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pynydus.api.schemas import (
    AgentSkill,
    Egg,
    HatchResult,
    Manifest,
    McpModule,
    MemoryModule,
    MemoryRecord,
    SecretsModule,
    SkillsModule,
)
from pynydus.common.enums import AgentType, MemoryLabel
from pynydus.llm import LLMTierConfig

# ---------------------------------------------------------------------------
# Hatch-to-disk helper (shared by hatcher tests)
# ---------------------------------------------------------------------------


def _hatch_to_disk(hatcher, egg: Egg, output_dir: Path) -> HatchResult:
    """Render an Egg via *hatcher* and write the files to *output_dir*.

    Returns a :class:`HatchResult` with the created file list.
    """
    result = hatcher.render(egg, output_dir)

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
    skills: list[AgentSkill] | None = None,
    memory: list[MemoryRecord] | None = None,
    nydus_version: str = "0.0.7",
    mcp: McpModule | None = None,
    secrets: SecretsModule | None = None,
    a2a_card: dict[str, Any] | None = None,
    agents_md: str | None = None,
    apm_yml: str | None = None,
    spec_snapshots: dict[str, str] | None = None,
    **manifest_kw,
) -> Egg:
    """Build an :class:`Egg` with sensible defaults.

    Pass ``skills`` / ``memory`` to override the default single-record modules.
    Egg-level fields (``mcp``, ``secrets``, ``a2a_card``, ``agents_md``,
    ``apm_yml``, ``spec_snapshots``) are set directly on the Egg.
    Extra *manifest_kw* are forwarded to :class:`Manifest`.
    """
    if skills is None:
        skills = [
            AgentSkill(
                name="test",
                description="Test skill.",
                body="Test skill.",
                metadata={"id": "skill_001", "source_framework": "markdown_skill"},
            )
        ]

    if memory is None:
        memory = [
            MemoryRecord(
                id="mem_001",
                text="A fact.",
                label=MemoryLabel.STATE,
                agent_type="openclaw",
                source_store="MEMORY.md",
            )
        ]

    manifest_kw.setdefault("created_at", datetime.now(UTC))

    egg_kw: dict[str, Any] = {
        "manifest": Manifest(
            nydus_version=nydus_version,
            agent_type=agent_type,
            **manifest_kw,
        ),
        "skills": SkillsModule(skills=skills),
        "memory": MemoryModule(memory=memory),
    }
    if mcp is not None:
        egg_kw["mcp"] = mcp
    if secrets is not None:
        egg_kw["secrets"] = secrets
    if a2a_card is not None:
        egg_kw["a2a_card"] = a2a_card
    if agents_md is not None:
        egg_kw["agents_md"] = agents_md
    if apm_yml is not None:
        egg_kw["apm_yml"] = apm_yml
    if spec_snapshots is not None:
        egg_kw["spec_snapshots"] = spec_snapshots

    return Egg(**egg_kw)


# ---------------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _wide_terminal(monkeypatch):
    monkeypatch.setenv("COLUMNS", "200")


@pytest.fixture
def sample_egg() -> Egg:
    """A basic Egg with 1 skill, 1 memory record: the most common test shape."""
    return make_egg()


@pytest.fixture
def minimal_egg() -> Egg:
    """An Egg with only a manifest and empty modules."""
    return make_egg(skills=[], memory=[])


@pytest.fixture
def llm_config() -> LLMTierConfig:
    """LLM tier for tests that need refinement."""
    return LLMTierConfig(
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        api_key="sk-ant-test",
    )
