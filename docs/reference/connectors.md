# Connectors

Spawners and hatchers map framework-specific files to the canonical Egg model
and back. For implementation details, see
{doc}`/advanced/adding-connectors`.

## Source connectors (spawners)

Spawners implement `parse(files: dict[str, str]) -> ParseResult`. They receive
pre-redacted file contents and return structured records.

### OpenClaw

| Source file | Becomes | Label |
|-------------|---------|-------|
| `SOUL.md` / `soul.md` / `IDENTITY.md` | `RawMemory` | **persona** |
| `AGENTS.md` / `agents.md` / `BOOT.md` / `HEARTBEAT.md` | `RawMemory` | **flow** |
| `USER.md` / `user.md` / `TOOLS.md` | `RawMemory` | **context** |
| `knowledge.md` / `MEMORY.md` / `memory/*.md` | `RawMemory` | **state** |
| `skill.md` / `skills.md` | `RawSkill` per heading | — |
| `skills/*.md` | `RawSkill` per file | — |
| `config.yaml` / `config.yml` / `config.json` | `SecretRecord` via gitleaks | — |
| `mcp.json` / `mcp/*.json` | MCP configs | — |

**Detection:** persona file or `skill.md` / `skills.md` / `skills/`.

### Letta

| Source | Becomes | Label |
|--------|---------|-------|
| `tools/*.py` | `RawSkill` | — |
| `agent_state.json` → `tools[]` | `RawSkill` | — |
| `agent_state.json` → `system` | `RawMemory` | **flow** |
| `agent_state.json` → `memory` blocks | `RawMemory` | per block |
| `system_prompt.md` / `.txt` | `RawMemory` | **flow** |
| `archival_memory.json` | `RawMemory` | **state** |
| `archival/*.{txt,md,json}` | `RawMemory` | **state** |
| `agent.db` (SQLite) | Skills + memory + secrets | — |

**Detection:** `.letta/`, `agent_state.json`, `agent.db`, or `tools/*.py`.

### ZeroClaw

| Source | Becomes | Label |
|--------|---------|-------|
| `SOUL.md` / `persona.md` / `IDENTITY.md` | `RawMemory` | **persona** |
| `AGENTS.md` / `instructions.md` / `system_prompt.md` / `HEARTBEAT.md` | `RawMemory` | **flow** |
| `USER.md` / `user.md` / `context.md` / `TOOLS.md` | `RawMemory` | **context** |
| `MEMORY.md` / `knowledge.md` / `memory/*.md` | `RawMemory` | **state** |
| `tools/*.py` | `RawSkill` | — |
| `tools.json` | `RawSkill` | — |
| `config.json` / `config.yaml` | `SecretRecord` via gitleaks | — |
| `mcp.json` / `mcp/*.json` | MCP configs | — |

**Detection:** `.zeroclaw/`, persona file, `tools/`/`tools.json`, or `AGENTS.md`.

## Target connectors (hatchers)

Hatchers implement `render(egg: Egg) -> RenderResult`. They produce file contents
with placeholders intact. All four `MemoryLabel` values have explicit file
mappings.

### OpenClaw

| Egg content | Output file |
|-------------|-------------|
| **persona** | `soul.md` |
| **flow** | `agents.md` |
| **context** | `user.md` |
| **state** | `knowledge.md` |
| Skills | `skill.md` (each as `# {name}`) |
| Secrets | `config.json` |
| MCP | `mcp/<name>.json` |

### Letta

| Egg content | Output |
|-------------|--------|
| **persona** | `agent_state.json` → `memory.persona.value` |
| **context** | `agent_state.json` → `memory.human.value` |
| **flow** | `agent_state.json` → `system` + `system_prompt.md` |
| **state** | `archival_memory.json` |
| Skills | `tools/<slug>.py` + `agent_state.json` tool refs |
| Secrets | `.letta/config.json` |

### ZeroClaw

| Egg content | Output |
|-------------|--------|
| **persona** | `persona.md` |
| **flow** | `agents.md` |
| **context** | `user.md` |
| **state** | `knowledge.md` |
| Skills | `tools/<slug>.py` |
| Secrets | `config.json` |
| MCP | `mcp/<name>.json` |
