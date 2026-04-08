# Letta Agent Specification

A Letta agent is defined by a JSON-based state file, optional Python
tool files, and archival memory. Supports both directory-based exports
and SQLite database inputs.

## Core State

| File | Purpose |
|------|---------|
| agent_state.json | Primary agent definition. Contains system prompt, memory blocks, tool definitions, and agent configuration. |
| *.af | Letta AgentFile — portable agent format containing all state in a single JSON file. |

### Memory Blocks (inside agent_state.json)

| Block | Purpose |
|-------|---------|
| memory.persona | Agent's self-description and personality. Maps to PERSONA label. |
| memory.human | Information about the user. Maps to CONTEXT label. |
| memory.system | System-level instructions. Maps to FLOW label. |
| memory.* (other) | Additional custom blocks. Map to CONTEXT label. |
| system | Top-level system prompt. Maps to FLOW label. |

## Archival Memory

| File | Purpose |
|------|---------|
| archival_memory.json | Long-term archival memory. Array of `{text, timestamp}` entries. Maps to STATE label. |
| archival/*.txt | Text-based archival entries, one per file. Maps to STATE label. |
| archival/*.md | Markdown archival entries. Maps to STATE label. |
| archival/*.json | JSON archival entries (array of objects or strings). Maps to STATE label. |

## Tools

| File | Purpose |
|------|---------|
| tools/*.py | Python tool files with docstrings and type hints. One function per file preferred. |
| tools[] (in agent_state.json) | Inline tool definitions with `name` and `source_code` fields. |

## Configuration

| File | Purpose |
|------|---------|
| .letta/ | Marker directory indicating a Letta project. |
| .letta/config.json | Letta configuration, may contain API keys and endpoints. |
| system_prompt.md / .txt | Fallback system prompt if not present in agent_state.json. |

## Database Mode

| Table | Purpose |
|-------|---------|
| blocks | Memory blocks (persona, human, system, custom). |
| archival_memory | Long-term archival memory entries. |
| tools | Tool definitions with source code. |
| agents | Agent configuration JSON. |

## Conventions

- agent_state.json is the single source of truth when present.
- Memory blocks have character limits — keep persona and human blocks concise.
- Python tools should have proper docstrings and type hints for the Letta runtime.
- The system prompt in agent_state.json takes precedence over system_prompt.md/txt.
- Archival memory is append-only in practice; entries accumulate over the agent's lifetime.
- Tool definitions in agent_state.json and tools/*.py are merged (disk files take precedence).
