# Agent Skills Spec

Spec version: 1.0
Source: https://agentskills.io/specification

## Overview

Agent Skills is an open standard for packaging reusable workflows and
expertise for AI agents. A skill is a directory containing a `SKILL.md`
file with YAML frontmatter and Markdown instructions.

Skills use a three-level progressive disclosure pattern:

1. **Metadata** — `name` and `description` loaded at startup (~100 tokens)
2. **Instructions** — Full `SKILL.md` body loaded when the skill activates
   (recommended < 5000 tokens)
3. **Resources** — Files in `scripts/`, `references/`, `assets/` loaded
   on-demand via tool calls

## Directory Structure

```
skill-name/
├── SKILL.md          # Required: metadata + instructions
├── scripts/          # Optional: executable code
├── references/       # Optional: documentation
└── assets/           # Optional: templates, resources
```

## SKILL.md Format

The file contains optional YAML frontmatter (between `---` fences) followed
by a Markdown body.

### Frontmatter Fields

| Field | Required | Type | Constraints |
|-------|----------|------|-------------|
| `name` | Yes | `string` | 1–64 chars; lowercase alphanumeric + hyphens; no leading/trailing/consecutive hyphens; must match directory name |
| `description` | Yes | `string` | 1–1024 chars; what the skill does and when to trigger it |
| `version` | No | `string` | SemVer string, defaults to "1.0" |
| `license` | No | `string` | SPDX identifier or reference to bundled LICENSE |
| `compatibility` | No | `array[string]` | Environment / system requirements (max 500 chars total) |
| `allowed-tools` | No | `string` | Space-separated list of pre-approved tools (experimental) |
| `metadata` | No | `object` | Arbitrary key-value pairs |

### Example

```yaml
---
name: code-review
description: Reviews pull requests for common issues and suggests improvements.
version: "1.2"
license: MIT
compatibility:
  - python>=3.10
  - git>=2.40
metadata:
  author: nydus
  source_framework: openclaw
---

# Code Review Skill

When asked to review code, follow these steps:
1. Check for common anti-patterns
2. Verify test coverage
3. Suggest improvements
```

## Nydus Conventions

- Skills are stored in the egg archive under `skills/<slug>/SKILL.md`.
- The `AgentSkill` Pydantic model is the canonical in-memory representation.
- Nydus-specific fields (`id`, `agent_type`, `source_framework`) are stored
  in the `metadata` map to keep frontmatter spec-compliant.
- A companion `nydus.json` at the archive root maps skill slugs to internal
  IDs and agent types.
- Skills are fully deterministic — no LLM involvement in skill packaging.

## Validation Schema

<!-- nydus:schema agent_skill -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://nydus.dev/schemas/agent-skill.json",
  "title": "Agent Skill (agentskills.io)",
  "description": "Validation schema for a single Agent Skill SKILL.md frontmatter.",
  "type": "object",
  "required": ["name", "description"],
  "properties": {
    "name": {
      "type": "string",
      "minLength": 1,
      "maxLength": 64,
      "pattern": "^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
      "description": "Slug-style identifier. Must match the containing directory name."
    },
    "description": {
      "type": "string",
      "minLength": 1,
      "maxLength": 1024,
      "description": "What the skill does and when to trigger it."
    },
    "version": {
      "type": "string",
      "description": "SemVer version string."
    },
    "license": {
      "type": "string",
      "description": "SPDX license identifier."
    },
    "compatibility": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Environment or system requirements."
    },
    "allowed-tools": {
      "type": "string",
      "description": "Space-separated list of pre-approved tool names (experimental)."
    },
    "metadata": {
      "type": "object",
      "additionalProperties": true,
      "description": "Arbitrary key-value pairs for extension data."
    }
  },
  "additionalProperties": false
}
```
<!-- /nydus:schema -->
