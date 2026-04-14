# ZeroClaw Agent

## Spawner: source files → Egg

| Source file | Egg field | Label |
|---|---|---|
| `SOUL.md` / `persona.md` / `IDENTITY.md` | `MemoryRecord` (one per paragraph) | `PERSONA` |
| `AGENTS.md` / `agents.md` / `instructions.md` / `system_prompt.md` / `HEARTBEAT.md` | `MemoryRecord` (one per paragraph) | `FLOW` |
| `USER.md` / `user.md` / `context.md` / `TOOLS.md` | `MemoryRecord` (one per paragraph) | `CONTEXT` |
| `MEMORY.md` / `knowledge.md` / `memory/*.md` | `MemoryRecord` (one per paragraph) | `STATE` |
| `tools/*.py` | `AgentSkill` | |
| `tools.json` | `AgentSkill` (fallback if no `tools/*.py`) | |
| `config.json` | `SecretRecord` (key/secret/token/password/auth values) | |
| `config.yaml` / `config.yml` | `SecretRecord` (regex-matched credentials) | |
| `mcp.json` | `McpModule` (raw server configs, Claude Desktop format) | |

Raw artifacts: all root `*.md`, `*.yaml`, `*.yml`, `*.json`, `*.txt` files
plus `tools/*.py`.

Detection: directory containing a `.zeroclaw` marker, or any persona file
(`SOUL.md`, `persona.md`, `IDENTITY.md`), or `tools/`/`tools.json`, or
`AGENTS.md`.

## Hatcher: Egg → target files

| Egg field | Target file | Notes |
|---|---|---|
| `MemoryRecord` (`PERSONA`) | `persona.md` | Joined with double newlines |
| `MemoryRecord` (`FLOW`) | `agents.md` | Joined with double newlines |
| `MemoryRecord` (`CONTEXT`) | `user.md` | Joined with double newlines |
| `MemoryRecord` (`STATE`) | `knowledge.md` | Joined with double newlines |
| `AgentSkill` | `tools/<name>.py` | One file per skill |
| `SecretRecord` (`CREDENTIAL`) | `config.json` | `{name: placeholder}` |
| `McpModule` | `mcp.json` | Claude Desktop format |

The hatcher also creates an empty `.zeroclaw/` marker directory.
