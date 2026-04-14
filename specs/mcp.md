# MCP Server Configuration Spec

Spec version: 2025-11-05 (latest protocol revision)
Source: https://modelcontextprotocol.io/
Config convention: Claude Desktop (de facto standard)

## Overview

The Model Context Protocol (MCP) defines a standard for connecting AI agents
to external tools and data sources through "MCP servers." Each server exposes
tools, resources, and/or prompts that an agent can invoke at runtime.

There is **no official config-file spec** for MCP
([open issue](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/292)).
Nydus follows the **Claude Desktop de facto convention** until one is
ratified. The same format is used by Cursor, Windsurf, and other clients.

## Claude Desktop Config Format

The canonical shape is a single JSON object with a top-level `mcpServers`
key whose value is a map of server-name → server-config:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "env": {}
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-brave"],
      "env": { "BRAVE_API_KEY": "{{BRAVE_API_KEY}}" }
    }
  }
}
```

### Server Config Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `command` | `string` | Yes (stdio) | Executable to launch the server |
| `args` | `array[string]` | No | Command-line arguments |
| `env` | `object` | No | Environment variables passed to the server |
| `url` | `string` | Yes (SSE/streamable-HTTP) | SSE or HTTP endpoint URL |
| `transport` | `string` | No | `"stdio"` (default), `"sse"`, or `"streamable-http"` |

Stdio servers require `command`; remote servers require `url`. Both may
coexist under different names in the same config.

## Nydus Conventions

- The egg stores a single **`mcp.json`** at the archive root.
- Content of each server config is preserved **verbatim** as raw
  `dict[str, Any]` — no typed model, no field-level parsing.
- During spawn, two source layouts are accepted:
  1. Combined `mcp.json` (with or without the `mcpServers` wrapper)
  2. Individual `mcp/<name>.json` files — merged into one `mcp.json`
- `nydus extract mcp` outputs a file directly usable as a Claude Desktop
  or Cursor config.
- When code needs a known field (e.g., `inspect` showing server command),
  it reads `.get("command")` on the raw dict.
- Validation is performed against the schema below, but is advisory —
  unknown fields are preserved, not rejected.

## Validation Schema

<!-- nydus:schema mcp_config -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://nydus.dev/schemas/mcp-config.json",
  "title": "MCP Config (Claude Desktop Format)",
  "description": "MCP server configuration following the Claude Desktop de facto convention.",
  "type": "object",
  "required": ["mcpServers"],
  "additionalProperties": false,
  "properties": {
    "mcpServers": {
      "type": "object",
      "description": "Map of server name to server configuration.",
      "additionalProperties": {
        "$ref": "#/$defs/McpServerConfig"
      }
    }
  },
  "$defs": {
    "McpServerConfig": {
      "type": "object",
      "description": "Configuration for a single MCP server. Stdio servers need command; remote servers need url.",
      "properties": {
        "command": {
          "type": "string",
          "description": "Executable to launch the server (stdio transport)."
        },
        "args": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Command-line arguments for the server process."
        },
        "env": {
          "type": "object",
          "additionalProperties": { "type": "string" },
          "description": "Environment variables passed to the server."
        },
        "url": {
          "type": "string",
          "format": "uri",
          "description": "Endpoint URL for SSE or streamable-HTTP transport."
        },
        "transport": {
          "type": "string",
          "enum": ["stdio", "sse", "streamable-http"],
          "description": "Transport mechanism. Defaults to stdio when command is present."
        }
      },
      "anyOf": [
        { "required": ["command"] },
        { "required": ["url"] }
      ],
      "additionalProperties": true
    }
  }
}
```
<!-- /nydus:schema -->
