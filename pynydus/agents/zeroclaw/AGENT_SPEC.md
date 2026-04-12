# ZeroClaw Workspace Specification

A ZeroClaw agent workspace is a directory of markdown files, Python
tools, and TOML configuration that defines the agent's persona,
instructions, memory, and capabilities.

References:

- <https://www.mintlify.com/zeroclaw-labs/zeroclaw/concepts/architecture>: System architecture
- <https://www.mintlify.com/zeroclaw-labs/zeroclaw/concepts/tools>: Tool system
- <https://www.mintlify.com/zeroclaw-labs/zeroclaw/concepts/memory>: Memory system
- <https://www.mintlify.com/zeroclaw-labs/zeroclaw/concepts/security>: Security architecture

## Persona Files

| File | Purpose |
|------|---------|
| SOUL.md / persona.md | Agent persona, personality, and tone. Maps to PERSONA label. |
| IDENTITY.md / identity.md | Agent name and identity. Maps to PERSONA label. Kept as a separate file on hatch. |
| identity.json | AIEOS-format identity (name, description, personality, vibe, backstory, role). Maps to PERSONA label. |

## Flow Files

| File | Purpose |
|------|---------|
| AGENTS.md / agents.md | Operating instructions, behavioral rules. Maps to FLOW label. |
| instructions.md | Alternative instructions file. Maps to FLOW label. |
| system_prompt.md | System prompt fallback. Maps to FLOW label. |
| HEARTBEAT.md | Heartbeat run checklist. Maps to FLOW label. |

## Context Files

| File | Purpose |
|------|---------|
| USER.md / user.md | User identity, preferences, context. Maps to CONTEXT label. |
| context.md | Additional context. Maps to CONTEXT label. |
| TOOLS.md / tools.md | Tool usage notes and environment-specific conventions. Maps to CONTEXT label. Kept as a separate file on hatch. |

## Memory Files

| File | Purpose |
|------|---------|
| MEMORY.md / knowledge.md | Curated long-term memory and knowledge base. Undated state records. Maps to STATE label. |
| memory/YYYY-MM-DD.md | Daily memory logs, one file per day. Dated state records. Maps to STATE label. |
| memory/session_*.md | Session-specific memory notes. Maps to STATE label. |
| memory.db | SQLite database with memory entries by category (Core, Daily, Conversation). |

## Tools

| File | Purpose |
|------|---------|
| tools/*.py | Python tool files. One tool per file, named with underscores (e.g. `search_web.py`). |
| tools.json | Tool manifest with metadata (fallback if no tools/*.py). |

### Tool Format

ZeroClaw's core tool system is defined by the `Tool` trait. Each tool
provides a name, description, JSON parameter schema, and an execute
method returning a structured `ToolResult`:

```python
class ExampleTool:
    def name(self) -> str:
        return "example_tool"

    def description(self) -> str:
        return "Short description of what this tool does"

    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The input query"
                }
            },
            "required": ["query"]
        }

    async def execute(self, args: dict) -> dict:
        # Validate inputs, perform operation, return result
        return {
            "success": True,
            "output": "result string",
            "error": None
        }
```

Key conventions:
- Each `.py` file should contain one self-contained tool.
- Tools return `ToolResult` dicts with `success` (bool), `output` (str), `error` (optional str).
- Parameter schemas use JSON Schema for type safety and LLM function calling.
- Tools validate inputs against `SecurityPolicy`: command allowlists, path validation, rate limiting.
- File tools check path permissions via `is_path_allowed()`.
- Shell tools enforce command allowlists and risk-level checks.

### Tool Categories

- **Default tools**: shell, file_read, file_write
- **Extended tools**: memory_store, memory_recall, memory_forget, http_request, web_fetch, browser, delegate
- **Scheduling tools**: cron_add, cron_list, cron_remove

## Configuration

| File | Purpose |
|------|---------|
| config.toml | **Primary** configuration format. Contains `[agent]` metadata (model, name, version), `[credentials]` placeholders, `[autonomy]` level, `[security]` policy, `[memory]` backend settings, `[gateway]` provider config. |
| config.json | Accepted by spawner as a fallback. Not the idiomatic format. |
| config.yaml / config.yml | Accepted by spawner as a fallback. Not the idiomatic format. |
| mcp.json / mcp/*.json | MCP server configurations. |
| .zeroclaw/ | Marker directory indicating a ZeroClaw project. Created by the hatcher. |

### config.toml Structure

```toml
[agent]
name = "my-agent"
model = "claude-3"
version = "0.1.0"

[credentials]
API_KEY = "{{SECRET_001}}"

[autonomy]
level = "full"              # full | supervised | read-only

[security]
workspace_only = true
forbidden_paths = ["~/.ssh", "~/.aws"]
block_high_risk_commands = false

[memory]
backend = "sqlite"          # sqlite | markdown
```

## Hatcher Output (Rebuild Mode)

The hatcher produces lowercase filenames and fans records back into
separate files using `source_store` metadata:

```
.zeroclaw/              <- marker directory
persona.md              <- PERSONA records (excluding identity)
identity.md             <- PERSONA records from IDENTITY.md / identity.json
agents.md               <- FLOW records
user.md                 <- CONTEXT records (excluding tools notes)
tools.md                <- CONTEXT records from TOOLS.md
knowledge.md            <- undated STATE records
memory/YYYY-MM-DD.md    <- dated STATE records (one file per day)
tools/*.py              <- skill records as Python tool files
config.toml             <- credential placeholders + round-tripped source metadata
mcp/*.json              <- MCP server configs
```

## Conventions

- Both UPPERCASE (SOUL.md, AGENTS.md) and lowercase (persona.md, agents.md) filenames are recognized by the spawner.
- Hatcher output uses **lowercase** filenames: persona.md, identity.md, agents.md, user.md, tools.md, knowledge.md.
- Markdown content is split by paragraphs -- each paragraph becomes a separate memory record.
- Python tools should be self-contained with clear function signatures and JSON parameter schemas.
- tools.json is only used when no tools/*.py files exist.
- Memory entries from memory.db are categorized by type (Core, Daily, Conversation), all mapping to STATE label.
- The `.zeroclaw/` marker directory is created by the hatcher for project detection.
- `source_store` on MemoryRecord preserves origin info, enabling the hatcher to reconstruct separate files (e.g. IDENTITY.md content stays in identity.md, not merged into persona.md).
