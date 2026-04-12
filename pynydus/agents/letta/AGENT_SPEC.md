# Letta Agent Specification

A Letta agent is defined by a `.af` AgentFile: Letta's open standard for
serializing stateful agents into a single portable JSON file.

References:

- <https://docs.letta.com/guides/core-concepts/agent-file/>: AgentFile concept guide
- <https://github.com/letta-ai/letta/blob/main/letta/schemas/agent_file.py>: AgentFileSchema source
- <https://github.com/letta-ai/agent-file>: Agent File specification repository

## AgentFile (.af): Canonical Format

The `.af` file follows the `AgentFileSchema` with these top-level keys:

| Key | Type | Purpose |
|-----|------|---------|
| `agents` | list | Agent definitions. Typically one agent per file. |
| `blocks` | list | Memory blocks referenced by agents (persona, human, custom). |
| `tools` | list | Tool definitions (custom Python tools + built-in references). |
| `mcp_servers` | list | MCP server configurations for external tool access. |
| `skills` | list | Skill packages with `SKILL.md` files and source URLs. |
| `groups` | list | Multi-agent group definitions. |
| `files` | list | Attached file references. |
| `sources` | list | Data source references. |
| `metadata` | dict | Arbitrary metadata (e.g. nydus provenance). |

### Agent Object (`agents[0]`)

| Field | Purpose |
|-------|---------|
| `name` | Agent display name. |
| `system` | System prompt text. Maps to FLOW label. |
| `agent_type` | Runtime type (e.g. `letta_v1_agent`). |
| `block_ids` | References to blocks in the top-level `blocks` list. |
| `tool_ids` | References to tools in the top-level `tools` list. |
| `tool_rules` | Behavioral sequencing constraints for tool calls. |
| `tool_exec_environment_variables` | Environment variables for tool execution (credential placeholders). |
| `messages` | Message history. Each message has `content` as a list of `{type, text}` objects. |
| `llm_config` | LLM configuration (model, endpoint, context window). |
| `embedding_config` | Embedding model configuration. |
| `tags` | Agent tags for organization. |

### Block Labels and Memory Mapping

| Block Label | Nydus MemoryLabel | Purpose |
|-------------|-------------------|---------|
| `persona` / `soul` | PERSONA | Agent's self-description and personality. |
| `human` / `about_user` / `preferences` | CONTEXT | Information about the user. |
| `custom_instructions` | FLOW | Custom behavioral instructions. |
| `scratchpad` / `active_hypotheses` / `conversation_patterns` / `learned_corrections` | STATE | Working memory and learned state. |
| *(other)* | CONTEXT | Any unrecognized block label defaults to CONTEXT. |

### Tool Types

| `tool_type` | Behavior |
|-------------|----------|
| `custom` | User-defined Python tools with `source_code`. Extracted as skill records. |
| `letta_core` | Built-in Letta tools (e.g. `send_message`). `source_code` is null. Skipped during spawn. |
| `letta_builtin` | Built-in Letta tools. `source_code` is null. Skipped during spawn. |
| `letta_sleeptime_core` | Sleep-time tools. `source_code` is null. Skipped during spawn. |

## Hatcher Output

The hatcher produces:

| File | Purpose |
|------|---------|
| `agent.af` | Single AgentFile containing the full agent state. Importable by Letta via `letta.agents.import_file()`. |
| `archival_memory.json` | Supplemental file for STATE memory (passages). The `.af` spec does not yet support archival passages. |

## Legacy Formats (Spawner Fallbacks)

The spawner also supports legacy directory-based exports for backward
compatibility. These are used only when no `.af` file is present.

| File | Purpose |
|------|---------|
| `agent_state.json` | Primary agent definition with system prompt, memory blocks, and inline tools. |
| `tools/*.py` | Python tool files. |
| `archival_memory.json` | Long-term archival memory entries. |
| `archival/*.txt` / `*.md` | Text-based archival entries. |
| `system_prompt.md` / `.txt` | Fallback system prompt. |
| `.letta/` | Marker directory. |

### Database Mode

| Table | Purpose |
|-------|---------|
| `blocks` | Memory blocks. |
| `archival_memory` | Archival memory entries. |
| `tools` | Tool definitions with source code. |
| `agents` | Agent configuration. |

## Conventions

- The `.af` file is the canonical, importable format. Prefer it over directory-based exports.
- Memory blocks have character limits (typically 5000). Keep persona and human blocks concise.
- Python tools should have proper docstrings and type hints for the Letta runtime.
- Only custom tools (with `source_code`) are extracted as skills. Built-in tools are skipped.
- Message `content` in `.af` is always a list of `{type, text}` objects, never a plain string.
- Archival memory is append-only in practice. Entries accumulate over the agent's lifetime.
