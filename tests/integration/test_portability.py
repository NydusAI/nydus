"""Integration tests: 3x3 agent portability matrix.

Each test: spawn from source fixtures -> save -> load -> hatch to target -> assert.
Marked ``@pytest.mark.integration`` — requires ``gitleaks`` on PATH.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pynydus.common.enums import AgentType
from pynydus.engine.hatcher import hatch
from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective
from pynydus.engine.packager import load, save
from pynydus.engine.pipeline import spawn

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Source fixtures
# ---------------------------------------------------------------------------

AGENT_TYPES = [AgentType.OPENCLAW, AgentType.ZEROCLAW, AgentType.LETTA]


def _write_openclaw(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "SOUL.md").write_text("I am a research assistant.\n\nI prefer concise summaries.\n")
    (d / "AGENTS.md").write_text("Follow structured output format.\n")
    (d / "USER.md").write_text("User prefers Python and Linux.\n")
    (d / "MEMORY.md").write_text("Python 3.12 released Oct 2023.\n")
    (d / "skill.md").write_text("# Summarize\n\nProduce a 5-bullet summary.\n")
    return d


def _write_zeroclaw(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "SOUL.md").write_text("I am a personal AI assistant.\n")
    (d / "AGENTS.md").write_text("Follow structured output.\n")
    (d / "USER.md").write_text("User likes Rust.\n")
    (d / "MEMORY.md").write_text("Learned async patterns yesterday.\n")
    tools_dir = d / "tools"
    tools_dir.mkdir()
    (tools_dir / "search.py").write_text(
        'def search(query: str) -> str:\n    """Search."""\n    return query\n'
    )
    return d


def _write_letta(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    af = {
        "agents": [
            {
                "id": "agent-0",
                "name": "test_bot",
                "system": "You are a helpful assistant.",
                "agent_type": "letta_v1_agent",
                "block_ids": ["blk-0", "blk-1"],
                "tool_ids": ["tool-0"],
                "tool_rules": [],
                "tags": [],
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "GPT-4 released 2023."}],
                    },
                ],
                "in_context_message_ids": [],
                "tool_exec_environment_variables": {},
            }
        ],
        "blocks": [
            {"id": "blk-0", "label": "persona", "value": "I study ML.", "limit": 5000},
            {"id": "blk-1", "label": "human", "value": "PhD student.", "limit": 5000},
        ],
        "tools": [
            {
                "id": "tool-0",
                "name": "greet",
                "source_code": "def greet(): pass",
                "tool_type": "custom",
                "source_type": "python",
            },
        ],
        "groups": [],
        "files": [],
        "sources": [],
        "mcp_servers": [],
        "metadata": {},
    }
    (d / "agent.af").write_text(json.dumps(af, indent=2))
    return d


_WRITERS = {
    AgentType.OPENCLAW: _write_openclaw,
    AgentType.ZEROCLAW: _write_zeroclaw,
    AgentType.LETTA: _write_letta,
}

# Expectations per target for a non-empty egg
_TARGET_EXPECTED_FILES = {
    AgentType.OPENCLAW: {"SOUL.md", "MEMORY.md"},
    AgentType.ZEROCLAW: {"persona.md", "knowledge.md", ".zeroclaw/.keep"},
    AgentType.LETTA: {"agent.af"},
}


# ---------------------------------------------------------------------------
# Matrix test
# ---------------------------------------------------------------------------


@pytest.fixture(params=AGENT_TYPES, ids=lambda t: t.value)
def source_type(request):
    return request.param


@pytest.fixture(params=AGENT_TYPES, ids=lambda t: t.value)
def target_type(request):
    return request.param


def test_portability(source_type: AgentType, target_type: AgentType, tmp_path: Path):
    """Spawn -> save -> load -> hatch for every source x target pair."""
    src_dir = tmp_path / "source"
    _WRITERS[source_type](src_dir)

    config = NydusfileConfig(
        sources=[SourceDirective(agent_type=source_type.value, path=str(src_dir))],
        redact=True,
    )
    egg, raw_artifacts, logs = spawn(config, nydusfile_dir=tmp_path)

    egg_path = tmp_path / "test.egg"
    save(egg, egg_path, raw_artifacts=raw_artifacts, spawn_log=logs.get("spawn_log"))

    loaded = load(egg_path, include_raw=True)

    out_dir = tmp_path / "hatched"
    result = hatch(
        loaded,
        target=target_type,
        output_dir=out_dir,
        raw_artifacts=loaded.raw_artifacts or raw_artifacts,
    )

    assert result.output_dir.exists()
    assert len(result.files_created) >= 1

    for expected_file in _TARGET_EXPECTED_FILES[target_type]:
        assert expected_file in result.files_created, (
            f"Expected {expected_file} in output for {source_type} -> {target_type}"
        )

    assert loaded.skills.skills or loaded.memory.memory, "Egg should not be empty"

    for skill in loaded.skills.skills:
        assert skill.content, f"Skill {skill.name} has empty content"
    for mem in loaded.memory.memory:
        assert mem.text, f"Memory {mem.id} has empty text"

    if loaded.secrets.secrets:
        all_output = " ".join(
            (out_dir / f).read_text() for f in result.files_created if (out_dir / f).exists()
        )
        for sec in loaded.secrets.secrets:
            if sec.required_at_hatch:
                assert sec.placeholder in all_output, (
                    f"Unreplaced placeholder {sec.placeholder} should be present "
                    f"(no secrets file provided)"
                )
