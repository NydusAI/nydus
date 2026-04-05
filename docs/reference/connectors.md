# Connectors

Connectors are the bridge between framework-specific file layouts and the
portable Egg format. Each supported platform has a **spawner** (reads source
files into the Egg) and a **hatcher** (writes Egg contents back to files).

For how to implement a new connector, see {doc}`/advanced/adding-connectors`.

## How connectors fit in the pipeline

```text
Source files                                           Target files
     │                                                      ▲
     ▼                                                      │
 ┌──────────┐    ┌──────────┐    ┌───┐    ┌──────────┐    ┌──────────┐
 │ Redaction │ -> │ Spawner  │ -> │Egg│ -> │ Hatcher  │ -> │ Secrets  │
 │ (gitleaks │    │ .parse() │    │   │    │ .render()│    │ injection│
 │  presidio)│    │          │    │   │    │          │    │          │
 └──────────┘    └──────────┘    └───┘    └──────────┘    └──────────┘

 Spawner receives        Spawner returns         Hatcher receives
 redacted file           skills + memory         the full Egg and
 contents (never         as structured           produces files with
 real secrets).          records.                placeholders intact.
```

**Spawners** implement `parse(files) -> ParseResult`:
- Input: `dict[str, str]` of filename to content. All secrets and PII have
  already been replaced with `{{SECRET_NNN}}` / `{{PII_NNN}}` placeholders.
- Output: a `ParseResult` containing extracted **skills** (code, workflows,
  capabilities) and **memory** (persona, instructions, context, knowledge).
  Each memory record is tagged with a **label** (`persona`, `flow`, `context`,
  or `state`) that describes what role it plays.

**Hatchers** implement `render(egg) -> RenderResult`:
- Input: a full `Egg` with structured skills, memory, and secret placeholders.
- Output: a `dict[str, str]` of filename to content, with placeholders still
  intact. The pipeline handles secret injection afterward.

## Memory labels

Every memory record in an Egg has one of four labels. These labels determine
which file it maps to in each platform:

| Label | Meaning | Examples |
|-------|---------|----------|
| **persona** | Who the agent is. Identity, personality, tone. | "You are a helpful coding assistant who prefers concise answers." |
| **flow** | How the agent operates. System instructions, workflows, boot sequences. | "Always check the user's timezone before scheduling." |
| **context** | What the agent knows about its environment. User info, tool descriptions. | "The user works at Acme Corp and uses Python 3.12." |
| **state** | Accumulated knowledge. Episodic memory, notes, conversation history. | "2026-03-15: User asked about database migration." |

## OpenClaw

### Spawning (source files the spawner reads)

| Source file | Extracted as | Label |
|-------------|-------------|-------|
| `SOUL.md`, `soul.md`, `IDENTITY.md` | Memory (split by paragraphs) | **persona** |
| `AGENTS.md`, `agents.md`, `BOOT.md`, `HEARTBEAT.md` | Memory (split by paragraphs) | **flow** |
| `USER.md`, `user.md`, `TOOLS.md` | Memory (split by paragraphs) | **context** |
| `knowledge.md`, `MEMORY.md` | Memory (split by paragraphs) | **state** |
| `memory/*.md` | Memory (split by paragraphs, date extracted from filename) | **state** |
| `skill.md`, `skills.md` | Skills (split by `#` headings, one skill per section) | |
| `skills/*.md` | Skills (one skill per file, filename becomes skill name) | |
| `config.yaml`, `config.yml`, `config.json` | Scanned for secrets by gitleaks before parse | |
| `mcp.json`, `mcp/*.json` | MCP server configurations | |

**Detection:** directory contains a persona file (`SOUL.md`, `soul.md`, `IDENTITY.md`) or skill files (`skill.md`, `skills.md`, `skills/`).

### Hatching (files the hatcher produces)

| Egg content | Output file | Format |
|-------------|-------------|--------|
| **persona** memory | `soul.md` | Paragraphs joined with blank lines |
| **flow** memory | `agents.md` | Paragraphs joined with blank lines |
| **context** memory | `user.md` | Paragraphs joined with blank lines |
| **state** memory | `knowledge.md` | Paragraphs joined with blank lines |
| Skills | `skill.md` | Each skill as a `# Name` section |
| Credential secrets | `config.json` | JSON object of `{name: placeholder}` |
| MCP configs | `mcp/<name>.json` | One JSON file per server |

## Letta

### Spawning (source files the spawner reads)

| Source file | Extracted as | Label |
|-------------|-------------|-------|
| `agent_state.json` > `memory.persona` | Memory | **persona** |
| `agent_state.json` > `memory.human` | Memory | **context** |
| `agent_state.json` > `system` | Memory | **flow** |
| `agent_state.json` > `tools[]` | Skills (from `source_code` field) | |
| `system_prompt.md`, `system_prompt.txt` | Memory (fallback if not in agent_state) | **flow** |
| `tools/*.py` | Skills (one per file, filename becomes skill name) | |
| `archival_memory.json` | Memory (array of `{text, timestamp}`) | **state** |
| `archival/*.txt`, `*.md`, `*.json` | Memory | **state** |
| `agent.db` (SQLite) | Skills + memory + secrets from database tables | mixed |
| Config files | Scanned for secrets by gitleaks before parse | |

**Detection:** `.letta/` directory, `agent_state.json`, `agent.db`, or `tools/*.py`.

### Hatching (files the hatcher produces)

| Egg content | Output file | Format |
|-------------|-------------|--------|
| **persona** memory | `agent_state.json` > `memory.persona.value` | JSON memory block |
| **context** memory | `agent_state.json` > `memory.human.value` | JSON memory block |
| **flow** memory | `agent_state.json` > `system` + `system_prompt.md` | Both JSON field and standalone file |
| **state** memory | `archival_memory.json` | JSON array of `{text, timestamp}` |
| Skills | `tools/<name>.py` + `agent_state.json` > `tools[]` | Python files + JSON tool refs |
| Credential secrets | `.letta/config.json` | JSON object of `{name: placeholder}` |

## ZeroClaw

### Spawning (source files the spawner reads)

| Source file | Extracted as | Label |
|-------------|-------------|-------|
| `SOUL.md`, `persona.md`, `IDENTITY.md` | Memory (split by paragraphs) | **persona** |
| `identity.json` | Memory (from name/description/personality fields) | **persona** |
| `AGENTS.md`, `instructions.md`, `system_prompt.md`, `HEARTBEAT.md` | Memory (split by paragraphs) | **flow** |
| `USER.md`, `user.md`, `context.md`, `TOOLS.md` | Memory (split by paragraphs) | **context** |
| `MEMORY.md`, `knowledge.md` | Memory (split by paragraphs) | **state** |
| `memory/*.md` | Memory (split by paragraphs, date extracted from filename) | **state** |
| `memory.db` (SQLite) | Memory from database rows (Core/Daily/Conversation categories) | **state** |
| `tools/*.py` | Skills (one per file, filename becomes skill name) | |
| `tools.json` | Skills (from `name` + `source`/`description` fields) | |
| `config.json`, `config.yaml`, `config.toml` | Scanned for secrets by gitleaks before parse | |
| `mcp.json`, `mcp/*.json` | MCP server configurations | |

**Detection:** `.zeroclaw/` marker, persona file, `tools/`/`tools.json`, `AGENTS.md`, or `memory.db`.

### Hatching (files the hatcher produces)

| Egg content | Output file | Format |
|-------------|-------------|--------|
| **persona** memory | `persona.md` | Paragraphs joined with blank lines |
| **flow** memory | `agents.md` | Paragraphs joined with blank lines |
| **context** memory | `user.md` | Paragraphs joined with blank lines |
| **state** memory | `knowledge.md` | Paragraphs joined with blank lines |
| Skills | `tools/<name>.py` | One Python file per skill |
| Credential secrets | `config.json` | JSON object of `{name: placeholder}` |
| MCP configs | `mcp/<name>.json` | One JSON file per server |
