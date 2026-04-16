# AGENTS.md: Nydus

> Instructions for AI coding agents working on this repository.

## Project

Nydus is a portable state transport for AI agents. It packages agent state
(skills, memory, secrets, MCP configs) into `.egg` archives that can be
spawned from one framework and hatched into another.

**Package manager:** `uv` (see `pyproject.toml`)
**Python:** `>=3.10`
**License:** MIT

## Spawn yourself

If you want to make a portable copy of yourself using Nydus, read
[SKILL.md](SKILL.md) in this directory. It covers installation, creating a
Nydusfile, spawning an egg, and hatching into a target runtime. The rest of
this file is for agents contributing to the Nydus codebase itself.

## Commands

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest tests/

# Run a specific test file
uv run pytest tests/unit/test_standards.py -v

# Lint (ruff)
uv run ruff check pynydus/ tests/
uv run ruff format --check pynydus/ tests/

# Auto-fix lint issues
uv run ruff check --fix pynydus/ tests/
uv run ruff format pynydus/ tests/

# Extract artifacts from an egg
uv run nydus extract mcp --from agent.egg -o ./out
uv run nydus extract skills --from agent.egg -o ./out
uv run nydus extract a2a --from agent.egg -o ./out
uv run nydus extract apm --from agent.egg -o ./out
uv run nydus extract agents --from agent.egg -o ./out
uv run nydus extract specs --from agent.egg -o ./specs
uv run nydus extract all --from agent.egg -o ./extracted
```

## Architecture

```
pynydus/
  api/            # Pydantic models (schemas.py), skill format, protocols, errors
  agents/         # Per-platform connectors (openclaw/, letta/, zeroclaw/)
    <platform>/
      spawner.py  # Subclasses Spawner ABC, parses source files
      hatcher.py  # Subclasses Hatcher ABC, renders egg to target files
  engine/         # Core pipeline: pipeline.py, hatcher.py, packager.py, validator.py
  standards/      # Per-standard modules: mcp, skills, a2a, apm, agents_md
  cmd/            # Typer CLI (main.py)
  security/       # Gitleaks, Presidio, signing
  llm/            # LLM tier config and refinement
specs/            # Spec markdown files with embedded JSON Schema
tests/
  unit/           # Unit tests
  integration/    # Full pipeline tests
```

## Hatch output structure

Hatching produces a structured output directory. Standard artifacts live at
the root. Platform-specific runtime files go in `agent/`:

```
<output_dir>/
  AGENTS.md            # deployment runbook (egg-level)
  agent-card.json      # A2A card
  apm.yml              # APM manifest
  mcp.json             # MCP configs (Claude Desktop format)
  agent/               # platform-specific runtime files
    SOUL.md            # (OpenClaw example)
    AGENTS.md          # flow memory (different from root AGENTS.md)
    skills/
    mcp.json           # connector-produced MCP config
    config.json
  logs/
    hatch_log.json
```

This separation is enforced by `engine/hatcher.py` Step 5 (connector files
to `agent/`) and Step 6 (`_write_standard_artifacts` to root).

## Conventions

- All data models are Pydantic v2 (`BaseModel`).
- `AgentSkill` (from `api/skill_format.py`) is the canonical skill type.
  Nydus-specific fields (`id`, `source_framework`) go in `skill.metadata`.
- MCP configs are raw `dict[str, Any]` (no typed model). Stored as a
  single `mcp.json` in Claude Desktop format.
- Secret placeholders: `{{SECRET_NNN}}` for credentials, `{{PII_NNN}}` for PII.
- Every spawner subclasses `Spawner` ABC. Every hatcher subclasses `Hatcher` ABC.
- Version: `__version__` in `pynydus/__init__.py`. Egg spec version: `EGG_SPEC_VERSION`.
- CLI options all have short aliases (e.g. `-t`/`--target`, `-s`/`--secrets`).

## Boundaries

### Always do
- Run `uv run pytest tests/` before declaring a task complete.
- Keep `ruff` clean, no lint errors.
- When adding a new standard, create both a `specs/<name>.md` and a
  `pynydus/standards/<name>.py` module.

### Never do
- Don't add typed models for MCP config fields. Store raw dicts.
- Don't parse or validate `apm.yml` content. It's a pure passthrough.
- Don't commit real API keys or secrets (gitleaks will catch them).
- Don't use `SkillRecord` or `McpServerConfig`. These are deleted types.
