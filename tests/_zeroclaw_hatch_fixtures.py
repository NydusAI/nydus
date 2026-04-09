"""Shared fixtures for ZeroClaw hatch layout integration tests."""

from __future__ import annotations

from pathlib import Path

from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective
from pynydus.engine.packager import load, save
from pynydus.engine.pipeline import spawn

PERSONA = "Concise, technical, opinionated. Always show code examples.\n"
IDENTITY = "ZeroClaw Agent v2\n\nPersonal coding assistant.\n"
AGENTS = "# Protocol\n\n1. Read the question.\n2. Search memory.\n3. Respond with citations.\n"
USER = "Prefers Rust and systems programming. Uses Arch Linux.\n"
TOOLS = "Search API rate limit 100 req/min. Use async executor.\n"
KNOWLEDGE = "Tokio 1.37 is the latest stable async runtime.\n"
DAILY_0315 = "Discussed Tokio runtime internals. User wants epoll deep-dive.\n"
DAILY_0317 = "Configured custom async executor. Benchmarked vs tokio.\n"
TOOL_SEARCH = 'def search_web(query: str) -> str:\n    """Search the web."""\n    return query\n'
TOOL_FILE = (
    'def file_read(path: str) -> str:\n    """Read a file."""\n    return open(path).read()\n'
)
CONFIG_TOML = '[agent]\nmodel = "claude-3"\nname = "zc-agent"\nversion = "0.2.0"\n'


def write_rich_zeroclaw(d: Path) -> Path:
    """Create a rich ZeroClaw workspace with every canonical file type."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "SOUL.md").write_text(PERSONA)
    (d / "IDENTITY.md").write_text(IDENTITY)
    (d / "AGENTS.md").write_text(AGENTS)
    (d / "USER.md").write_text(USER)
    (d / "TOOLS.md").write_text(TOOLS)
    (d / "MEMORY.md").write_text(KNOWLEDGE)

    mem_dir = d / "memory"
    mem_dir.mkdir()
    (mem_dir / "2026-03-15.md").write_text(DAILY_0315)
    (mem_dir / "2026-03-17.md").write_text(DAILY_0317)

    tools_dir = d / "tools"
    tools_dir.mkdir()
    (tools_dir / "search_web.py").write_text(TOOL_SEARCH)
    (tools_dir / "file_read.py").write_text(TOOL_FILE)

    (d / "config.toml").write_text(CONFIG_TOML)

    marker = d / ".zeroclaw"
    marker.mkdir()

    return d


def spawn_rich_zeroclaw(tmp_path: Path):
    """Write, spawn, save, and load a rich ZeroClaw workspace.

    Returns (loaded_egg, raw_artifacts).
    """
    src = tmp_path / "source"
    write_rich_zeroclaw(src)

    config = NydusfileConfig(
        sources=[SourceDirective(agent_type="zeroclaw", path=str(src))],
        redact=False,
    )
    egg, raw_artifacts, logs = spawn(config, nydusfile_dir=tmp_path)
    egg_path = tmp_path / "test.egg"
    save(egg, egg_path, raw_artifacts=raw_artifacts, spawn_log=logs.get("spawn_log"))
    loaded = load(egg_path, include_raw=True)
    return loaded, raw_artifacts
