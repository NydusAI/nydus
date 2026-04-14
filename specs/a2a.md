# A2A Agent Card Spec

Spec version: 0.3 (A2A Protocol)
Source: https://a2a-protocol.org/latest/specification/

## Overview

The Agent2Agent (A2A) protocol enables communication and interoperability
between AI agents. Each agent advertises its capabilities through an
**Agent Card** — a machine-readable JSON manifest used for discovery,
capability advertisement, and interaction negotiation.

The standard location for discovery is `/.well-known/agent-card.json`.

## Agent Card Structure

### AgentCard

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | Yes | Human-readable display name |
| `description` | `string` | Yes | Detailed purpose and functionality |
| `version` | `string` | Yes | Semantic version of the agent implementation |
| `supportedInterfaces` | `array[AgentInterface]` | Yes | Ordered list of supported interfaces (first = preferred) |
| `provider` | `AgentProvider` | No | Service provider of the agent |
| `documentationUrl` | `string` | No | URL to additional documentation |
| `capabilities` | `AgentCapabilities` | Yes | A2A capability set |
| `securitySchemes` | `map[string, SecurityScheme]` | No | Authentication scheme details |
| `securityRequirements` | `array[SecurityRequirement]` | No | Security requirements for contacting the agent |
| `defaultInputModes` | `array[string]` | Yes | Supported input media types |
| `defaultOutputModes` | `array[string]` | Yes | Supported output media types |
| `skills` | `array[AgentSkill]` | Yes | Agent's capabilities / functions |
| `signatures` | `array[AgentCardSignature]` | No | JSON Web Signatures |
| `iconUrl` | `string` | No | URL to agent icon |

### AgentProvider

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | `string` | Yes | Provider website URL |
| `organization` | `string` | Yes | Provider organization name |

### AgentCapabilities

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `streaming` | `boolean` | No | Supports streaming responses |
| `pushNotifications` | `boolean` | No | Supports push notifications |
| `extensions` | `array[AgentExtension]` | No | Protocol extensions supported |
| `extendedAgentCard` | `boolean` | No | Supports extended agent card |

### AgentSkill (A2A)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | Yes | Unique identifier |
| `name` | `string` | Yes | Human-readable name |
| `description` | `string` | Yes | Detailed description |
| `tags` | `array[string]` | Yes | Keywords for capability matching |
| `examples` | `array[string]` | No | Example prompts or scenarios |
| `inputModes` | `array[string]` | No | Override default input modes |
| `outputModes` | `array[string]` | No | Override default output modes |
| `securityRequirements` | `array[SecurityRequirement]` | No | Skill-level security |

### AgentInterface

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | `string` | Yes | Endpoint URL (HTTPS in production) |
| `protocolBinding` | `string` | Yes | `JSONRPC`, `GRPC`, or `HTTP+JSON` |
| `tenant` | `string` | No | Tenant ID for multi-tenant deployments |
| `protocolVersion` | `string` | Yes | A2A protocol version (e.g. "0.3") |

## Nydus Conventions

- The egg stores a single **`agent-card.json`** at the archive root.
- **Passthrough first**: if the source project already contains
  `agent-card.json`, Nydus copies it verbatim into the egg.
- **Generate otherwise**: Nydus builds a card deterministically from egg
  data, with optional LLM enhancement for `name`, `description`, and
  skill descriptions.
- `supportedInterfaces` is left as an empty array — Nydus produces
  portable artifacts, not running services. Consumers fill in the
  endpoint at deploy time.
- `capabilities` defaults to `{streaming: false, pushNotifications: false}`.

### Deterministic Fallback

| Agent Card Field | Source in Egg |
|------------------|--------------|
| `name` | `manifest.agent_name` or `manifest.agent_type` |
| `description` | `manifest.agent_description` or first PERSONA memory |
| `version` | `manifest.egg_version` |
| `skills` | One entry per `AgentSkill` (name, tags from metadata) |
| `defaultInputModes` | `["text/plain"]` |
| `defaultOutputModes` | `["text/plain"]` |

## Validation Schema

<!-- nydus:schema a2a_agent_card -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://nydus.dev/schemas/a2a-agent-card.json",
  "title": "A2A Agent Card",
  "description": "Agent Card per the A2A protocol specification (v0.3).",
  "type": "object",
  "required": [
    "name",
    "description",
    "version",
    "supportedInterfaces",
    "capabilities",
    "defaultInputModes",
    "defaultOutputModes",
    "skills"
  ],
  "properties": {
    "name": {
      "type": "string",
      "minLength": 1,
      "description": "Human-readable display name."
    },
    "description": {
      "type": "string",
      "minLength": 1,
      "description": "Detailed purpose and functionality."
    },
    "version": {
      "type": "string",
      "description": "Semantic version of the agent implementation."
    },
    "supportedInterfaces": {
      "type": "array",
      "items": { "$ref": "#/$defs/AgentInterface" },
      "description": "Ordered list of supported interfaces."
    },
    "provider": {
      "$ref": "#/$defs/AgentProvider"
    },
    "documentationUrl": {
      "type": "string",
      "format": "uri"
    },
    "capabilities": {
      "$ref": "#/$defs/AgentCapabilities"
    },
    "securitySchemes": {
      "type": "object",
      "additionalProperties": true
    },
    "securityRequirements": {
      "type": "array",
      "items": { "type": "object" }
    },
    "defaultInputModes": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1
    },
    "defaultOutputModes": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1
    },
    "skills": {
      "type": "array",
      "items": { "$ref": "#/$defs/A2ASkill" }
    },
    "signatures": {
      "type": "array",
      "items": { "type": "object" }
    },
    "iconUrl": {
      "type": "string",
      "format": "uri"
    }
  },
  "additionalProperties": true,
  "$defs": {
    "AgentInterface": {
      "type": "object",
      "required": ["url", "protocolBinding", "protocolVersion"],
      "properties": {
        "url": { "type": "string", "format": "uri" },
        "protocolBinding": { "type": "string" },
        "tenant": { "type": "string" },
        "protocolVersion": { "type": "string" }
      },
      "additionalProperties": true
    },
    "AgentProvider": {
      "type": "object",
      "required": ["url", "organization"],
      "properties": {
        "url": { "type": "string" },
        "organization": { "type": "string" }
      },
      "additionalProperties": true
    },
    "AgentCapabilities": {
      "type": "object",
      "properties": {
        "streaming": { "type": "boolean" },
        "pushNotifications": { "type": "boolean" },
        "extensions": { "type": "array", "items": { "type": "object" } },
        "extendedAgentCard": { "type": "boolean" }
      },
      "additionalProperties": true
    },
    "A2ASkill": {
      "type": "object",
      "required": ["id", "name", "description", "tags"],
      "properties": {
        "id": { "type": "string" },
        "name": { "type": "string" },
        "description": { "type": "string" },
        "tags": { "type": "array", "items": { "type": "string" } },
        "examples": { "type": "array", "items": { "type": "string" } },
        "inputModes": { "type": "array", "items": { "type": "string" } },
        "outputModes": { "type": "array", "items": { "type": "string" } },
        "securityRequirements": { "type": "array", "items": { "type": "object" } }
      },
      "additionalProperties": true
    }
  }
}
```
<!-- /nydus:schema -->
