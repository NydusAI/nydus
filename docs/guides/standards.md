# Agentic Standards

Nydus integrates with five agentic standards. Each standard has a spec file
in `specs/`, a Python module in `pynydus/standards/`, validation against its
schema, and a CLI `extract` command.

## Overview

| Standard | Spec file | Egg artifact | Extract command |
|----------|-----------|--------------|-----------------|
| [MCP](https://modelcontextprotocol.io/) | `specs/mcp.md` | `mcp.json` | `nydus extract mcp` |
| [Agent Skills](https://agentskills.io) | `specs/agentskills.md` | `skills/<slug>/SKILL.md` | `nydus extract skills` |
| [A2A](https://a2a-protocol.org/latest/) | `specs/a2a.md` | `agent-card.json` | `nydus extract a2a` |
| [APM](https://microsoft.github.io/apm/) | `specs/apm.md` | `apm.yml` | `nydus extract apm` |
| [AGENTS.md](https://agents.md/) | `specs/agents.md` | `AGENTS.md` | `nydus extract agents` |

## Spec files

Each spec lives in `specs/<name>.md` as a Markdown file with an embedded
JSON Schema block fenced by `<!-- nydus:schema -->` markers. The prose
documents what Nydus expects; the schema enables machine validation.

During spawning (Step 10), all spec files are snapshotted into the egg as
`egg.spec_snapshots`, along with a `specs/manifest.json` recording the
spec version and source URL for each. This makes every egg self-sustained:
it carries the exact spec versions it was built against.

## Standards package (`pynydus/standards/`)

Each standard has a Python module that exposes up to three functions:

- **`validate(egg)`** — checks the egg's artifact against the spec's JSON Schema.
  Returns a list of `ValidationIssue`. Called by the egg validator during
  `inspect` and as a gate before `hatch`.
- **`extract(egg)`** — returns the standard's artifact as a `dict[str, str]`
  (filename → content). Called by `nydus extract <standard>`.
- **`generate(egg)`** — deterministically produces the artifact from egg data.
  Used during Step 10 when no source artifact exists. Not all standards have
  this (e.g. skills are parsed, not generated; APM is passthrough-only).

A shared helper, `validate_against_schema()` in `_loader.py`, centralizes
`jsonschema` validation so individual modules don't duplicate boilerplate.

### MCP

Stored as `mcp.json` in [Claude Desktop format](https://modelcontextprotocol.io/)
(`{"mcpServers": {...}}`). Configs are raw `dict[str, Any]` — Nydus does not
parse or normalize MCP beyond the top-level wrapper. Validated against the
embedded JSON Schema.

### Agent Skills

Skills are stored as `skills/<slug>/SKILL.md` files following the
[agentskills.io](https://agentskills.io) format. Each skill is an `AgentSkill`
object with name, description, body, version, and metadata. Validated against
the embedded schema.

### A2A (Agent Card)

The A2A agent card (`agent-card.json`) follows the
[A2A protocol](https://a2a-protocol.org/latest/). Nydus is **passthrough-first**:
if the source project contains `agent-card.json`, it is copied verbatim. Otherwise,
a deterministic card is generated from egg metadata (skills become capabilities,
manifest fields populate the card structure).

### APM

APM is **pure passthrough**. If `apm.yml` exists in the source, Nydus copies it
into the egg and writes it back out during hatch. No parsing, no validation,
no generation. Nydus only reserves a dedicated slot for it.

### AGENTS.md

A per-egg `AGENTS.md` deployment runbook is generated from the egg's contents:
skills, memory labels, MCP configs, and secret requirements. This is distinct
from the repo-level `AGENTS.md` (which guides AI agents consuming the Nydus
repository itself).

## Extracting artifacts

Use `nydus extract` to pull individual standards from an egg:

```bash
nydus extract mcp --from agent.egg -o ./out
nydus extract skills --from agent.egg -o ./out
nydus extract a2a --from agent.egg -o ./out
nydus extract apm --from agent.egg -o ./out
nydus extract agents --from agent.egg -o ./out
nydus extract specs --from agent.egg -o ./specs
nydus extract all --from agent.egg -o ./extracted
```

## Validation

Standard validation runs automatically during `nydus inspect` and as a gate
before `nydus hatch`. Each standard's `validate()` function checks its artifact
against the embedded JSON Schema. Issues are reported inline with structural
validation results.

There is no standalone `validate` CLI command — validation is integrated into
`inspect` and `hatch`.
