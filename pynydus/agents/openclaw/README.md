# OpenClaw Agent

## Spawner: source files → Egg

| Source file | Egg field | Label |
|---|---|---|
| `SOUL.md` / `soul.md` / `IDENTITY.md` | `MemoryRecord` (one per paragraph) | `PERSONA` |
| `AGENTS.md` / `agents.md` / `BOOT.md` / `HEARTBEAT.md` | `MemoryRecord` (one per paragraph) | `FLOW` |
| `USER.md` / `user.md` / `TOOLS.md` | `MemoryRecord` (one per paragraph) | `CONTEXT` |
| `knowledge.md` / `MEMORY.md` / `memory/*.md` | `MemoryRecord` (one per paragraph) | `STATE` |
| `skill.md` / `skills.md` | `AgentSkill` (split by `#` headings) | |
| `skills/*.md` | `AgentSkill` (one per file) | |
| `config.yaml` / `config.yml` | `SecretRecord` (regex-matched credentials) | |
| `config.json` | `SecretRecord` (key/secret/token/password values) | |
| `mcp.json` | `McpModule` (raw server configs, Claude Desktop format) | |

Raw artifacts: all root `*.md`, `*.yaml`, `*.yml`, `*.json`, `*.txt` files
plus `skills/*.md`.

Detection: directory containing any persona file (`SOUL.md`, `soul.md`, or
`IDENTITY.md`), or `skill.md`/`skills.md`, or a `skills/` subdirectory.

## Hatcher: Egg → target files

| Egg field | Target file | Notes |
|---|---|---|
| `MemoryRecord` (`PERSONA`) | `soul.md` | Joined with double newlines |
| `MemoryRecord` (`FLOW`) | `agents.md` | Joined with double newlines |
| `MemoryRecord` (`CONTEXT`) | `user.md` | Joined with double newlines |
| `MemoryRecord` (`STATE`) | `knowledge.md` | Joined with double newlines |
| `AgentSkill` | `skill.md` | `# name` sections |
| `SecretRecord` (`CREDENTIAL`) | `config.json` | `{name: placeholder}` |
| `McpModule` | `mcp.json` | Claude Desktop format |
