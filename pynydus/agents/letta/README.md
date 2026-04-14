# Letta Agent

## Spawner: source files → Egg

Supports both directory-based and SQLite database inputs.

### Directory mode

| Source file | Egg field | Label |
|---|---|---|
| `agent_state.json` → `system` | `MemoryRecord` | `FLOW` |
| `agent_state.json` → `memory.persona` | `MemoryRecord` | `PERSONA` |
| `agent_state.json` → `memory.human` | `MemoryRecord` | `CONTEXT` |
| `agent_state.json` → `memory.<other>` | `MemoryRecord` | `CONTEXT` |
| `agent_state.json` → `tools[]` | `AgentSkill` | |
| `system_prompt.md` / `.txt` | `MemoryRecord` (fallback if no system in state) | `FLOW` |
| `archival_memory.json` | `MemoryRecord` | `STATE` |
| `archival/*` | `MemoryRecord` | `STATE` |
| `tools/*.py` | `AgentSkill` | |
| `.letta/config.json` | `SecretRecord` | |

### Database mode (`agent.db`)

| DB table | Egg field | Label |
|---|---|---|
| `blocks` (persona) | `MemoryRecord` | `PERSONA` |
| `blocks` (human) | `MemoryRecord` | `CONTEXT` |
| `blocks` (system) | `MemoryRecord` | `FLOW` |
| `blocks` (other) | `MemoryRecord` | `CONTEXT` |
| `archival_memory` | `MemoryRecord` | `STATE` |
| `tools` | `AgentSkill` | |
| `agents` → config JSON | `SecretRecord` | |

Detection: directory with `agent_state.json`, `.letta/`, `tools/`, or
`agent.db`, or a `.db` file directly.

## Hatcher: Egg → target files

| Egg field | Target file | Notes |
|---|---|---|
| `MemoryRecord` (`PERSONA`) | `agent_state.json` → `memory.persona` | Appended to block value |
| `MemoryRecord` (`CONTEXT`) | `agent_state.json` → `memory.human` | Appended to block value |
| `MemoryRecord` (`FLOW`) | `agent_state.json` → `system` + `system_prompt.md` | Duplicate for convenience |
| `MemoryRecord` (`STATE`) | `archival_memory.json` | Array of `{text, timestamp}` |
| `AgentSkill` | `tools/<name>.py` + `agent_state.json` → `tools[]` | Source code in both |
| `SecretRecord` (`CREDENTIAL`) | `.letta/config.json` | `{name: placeholder}` |
