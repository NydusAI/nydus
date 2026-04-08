"""Shared fixtures for OpenClaw hatch layout integration tests."""

from __future__ import annotations

from pathlib import Path

from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective
from pynydus.engine.packager import load, save
from pynydus.engine.pipeline import spawn

SOUL = "Sharp, concise, no filler. Lead with the answer.\n"
IDENTITY = "Voyager\n\nPersonal travel concierge.\n"
AGENTS = "# Protocol\n\n1. Assess the request.\n2. Gather context.\n3. Respond.\n"
USER = "Prefers window seat and vegetarian meals.\n"
TOOLS = "Flight search API available. Rate limit 100 req/min.\n"
MEMORY = "Preferred car rental: gold plus rewards tier.\n"
DAILY_0401 = "Researched direct flights. Best option is 837 nonstop.\n"
DAILY_0403 = "Booked flight 837. Sent confirmation to user.\n"
SKILL_BOOK = "Search flights by origin, destination, dates. Present top 3 options.\n"
SKILL_HOTEL = "Search hotels by city and dates. Sort by value.\n"


def write_rich_openclaw(d: Path) -> Path:
    """Create a rich OpenClaw workspace with every canonical file type."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "SOUL.md").write_text(SOUL)
    (d / "IDENTITY.md").write_text(IDENTITY)
    (d / "AGENTS.md").write_text(AGENTS)
    (d / "USER.md").write_text(USER)
    (d / "TOOLS.md").write_text(TOOLS)
    (d / "MEMORY.md").write_text(MEMORY)

    mem_dir = d / "memory"
    mem_dir.mkdir()
    (mem_dir / "2026-04-01.md").write_text(DAILY_0401)
    (mem_dir / "2026-04-03.md").write_text(DAILY_0403)

    skills_dir = d / "skills"
    skills_dir.mkdir()
    (skills_dir / "book-flight.md").write_text(SKILL_BOOK)
    (skills_dir / "search-hotels.md").write_text(SKILL_HOTEL)

    return d


def spawn_rich_openclaw(tmp_path: Path):
    """Write, spawn, save, and load a rich OpenClaw workspace.

    Returns (loaded_egg, raw_artifacts).
    """
    src = tmp_path / "source"
    write_rich_openclaw(src)

    config = NydusfileConfig(
        sources=[SourceDirective(agent_type="openclaw", path=str(src))],
        redact=False,
    )
    egg, raw_artifacts, logs = spawn(config, nydusfile_dir=tmp_path)
    egg_path = tmp_path / "test.egg"
    save(egg, egg_path, raw_artifacts=raw_artifacts, spawn_log=logs.get("spawn_log"))
    loaded = load(egg_path, include_raw=True)
    return loaded, raw_artifacts
