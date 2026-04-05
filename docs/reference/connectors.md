# Connectors

Connectors bridge framework-specific file layouts and the portable Egg format.
Each supported platform has a **spawner** (reads source files into an Egg) and
a **hatcher** (writes Egg contents back to files).

For how to implement a new connector, see {doc}`/advanced/adding-connectors`.

## Pipeline overview

```text
Source files  →  Redaction  →  Spawner  →  Egg  →  Hatcher  →  Secret injection  →  Target files
```

- **Spawner** receives file contents after secrets and PII have been replaced
  with `{{SECRET_NNN}}` / `{{PII_NNN}}` placeholders. It extracts skills and
  memory records, each tagged with a label.

- **Hatcher** receives the full Egg and produces target files with placeholders
  still intact. The pipeline handles secret injection as the final step.

## Egg contents

Every Egg stores four types of content. The tables below show how each maps
to files in each platform.

| Content | Description |
|---------|-------------|
| Memory[**persona**] | Who the agent is: identity, personality, tone |
| Memory[**flow**] | How the agent operates: system instructions, workflows |
| Memory[**context**] | What the agent knows about its environment: user info, tool descriptions |
| Memory[**state**] | Accumulated knowledge: episodic memory, notes, conversation history |
| Skills | Code, workflows, and capabilities |
| Secrets | Credential and PII placeholders with injection metadata |
| MCP | MCP server configurations |

## OpenClaw


| Egg content | Spawner reads | Hatcher writes |
|-------------|---------------|----------------|
| Memory[**persona**] | `SOUL.md`, `soul.md`, `IDENTITY.md` | `soul.md` |
| Memory[**flow**] | `AGENTS.md`, `agents.md`, `BOOT.md`, `HEARTBEAT.md` | `agents.md` |
| Memory[**context**] | `USER.md`, `user.md`, `TOOLS.md` | `user.md` |
| Memory[**state**] | `knowledge.md`, `MEMORY.md`, `memory/*.md` | `knowledge.md` |
| Skills | `skill.md`, `skills.md`, `skills/*.md` | `skill.md` (each skill as a `# Name` section) |
| Secrets | `config.yaml`, `config.yml`, `config.json` | `config.json` |
| MCP | `mcp.json`, `mcp/*.json` | `mcp/<name>.json` |


**Detection:** persona file (`SOUL.md`, `soul.md`, `IDENTITY.md`) or skill
files (`skill.md`, `skills.md`, `skills/`).

## Letta


Letta stores memory in named blocks inside `agent_state.json`. The block names
differ from Egg labels: Letta calls context memory `human` and flow memory
`system`.


| Egg content | Spawner reads | Hatcher writes |
|-------------|---------------|----------------|
| Memory[**persona**] | `agent_state.json` > `memory.persona` | `agent_state.json` > `memory.persona.value` |
| Memory[**flow**] | `agent_state.json` > `system`, `system_prompt.md/.txt` | `agent_state.json` > `system` + `system_prompt.md` |
| Memory[**context**] | `agent_state.json` > `memory.human` | `agent_state.json` > `memory.human.value` |
| Memory[**state**] | `archival_memory.json`, `archival/*.{txt,md,json}` | `archival_memory.json` |
| Skills | `agent_state.json` > `tools[]`, `tools/*.py` | `tools/<name>.py` + `agent_state.json` > `tools[]` |
| Secrets | config files | `.letta/config.json` |


`agent.db` (SQLite) is also supported as a source. It contains skills, memory,
and secrets in database tables.


**Detection:** `.letta/` directory, `agent_state.json`, `agent.db`, or
`tools/*.py`.

## ZeroClaw


| Egg content | Spawner reads | Hatcher writes |
|-------------|---------------|----------------|
| Memory[**persona**] | `SOUL.md`, `persona.md`, `IDENTITY.md`, `identity.json` | `persona.md` |
| Memory[**flow**] | `AGENTS.md`, `instructions.md`, `system_prompt.md`, `HEARTBEAT.md` | `agents.md` |
| Memory[**context**] | `USER.md`, `user.md`, `context.md`, `TOOLS.md` | `user.md` |
| Memory[**state**] | `MEMORY.md`, `knowledge.md`, `memory/*.md`, `memory.db` | `knowledge.md` |
| Skills | `tools/*.py`, `tools.json` | `tools/<name>.py` |
| Secrets | `config.json`, `config.yaml`, `config.toml` | `config.json` |
| MCP | `mcp.json`, `mcp/*.json` | `mcp/<name>.json` |


**Detection:** `.zeroclaw/` marker, persona file, `tools/`/`tools.json`,
`AGENTS.md`, or `memory.db`.
