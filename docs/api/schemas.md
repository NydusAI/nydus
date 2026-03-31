# Data Models

Core Pydantic models for the Egg data structure. All types listed here are
importable from the top-level `pynydus` package or from `pynydus.api.schemas`.

## Egg

The top-level container. An Egg holds a manifest, a modules accessor (skills,
memory, secrets), optional MCP server configs, source metadata, and raw
artifact bytes.

```python
from pynydus import Egg

egg: Egg = ny.spawn()
egg.manifest          # Manifest with metadata
egg.modules.skills    # list[SkillRecord]
egg.modules.memory    # list[MemoryRecord]
egg.modules.secrets   # list[SecretRecord]
```

```{autodoc2-object} pynydus.api.schemas.Egg
```

```{autodoc2-object} pynydus.api.schemas.ModulesAccessor
```

## Manifest

Metadata about the Egg: source type, creation timestamp, egg_id, version,
build intent, redaction policy, and optional signature.

```{autodoc2-object} pynydus.api.schemas.Manifest
```

```{autodoc2-object} pynydus.api.schemas.RedactionPolicy
```

```{autodoc2-object} pynydus.api.schemas.SourceEntry
```

## Module containers

Typed wrappers around the three module lists. Used internally for serialization
and validation.

```{autodoc2-object} pynydus.api.schemas.SkillsModule
```

```{autodoc2-object} pynydus.api.schemas.MemoryModule
```

```{autodoc2-object} pynydus.api.schemas.SecretsModule
```

## Records

### SkillRecord

A single skill in the Agent Skills format. Contains a name, slug, content,
and optional metadata.

```{autodoc2-object} pynydus.api.schemas.SkillRecord
```

### MemoryRecord

A labeled chunk of agent memory. The `label` field uses `MemoryLabel` to
classify the record's semantic role (persona, flow, context, or state).

```{autodoc2-object} pynydus.api.schemas.MemoryRecord
```

### SecretRecord

A redacted credential or PII value. Contains the placeholder name (e.g.,
`SECRET_001`), kind (`credential` or `pii`), description, and occurrence
tracking metadata.

```{autodoc2-object} pynydus.api.schemas.SecretRecord
```

### McpServerConfig

Configuration for a Model Context Protocol server. Extracted from source
`mcp.json` or similar config files.

```{autodoc2-object} pynydus.api.schemas.McpServerConfig
```

## Pipeline results

Types returned by hatch, validate, and diff operations.

```{autodoc2-object} pynydus.api.schemas.HatchResult
```

```{autodoc2-object} pynydus.api.schemas.ValidationReport
```

```{autodoc2-object} pynydus.api.schemas.ValidationIssue
```

```{autodoc2-object} pynydus.api.schemas.DiffReport
```

```{autodoc2-object} pynydus.api.schemas.DiffEntry
```

```{autodoc2-object} pynydus.api.schemas.EggPartial
```

## Enums

### MemoryLabel

Four canonical labels that classify how agent memory is used:

| Label | Purpose |
|-------|---------|
| `persona` | Identity, personality, name, backstory |
| `flow` | System prompt, orchestration rules, behavioral instructions |
| `context` | User preferences, tool descriptions, environment info |
| `state` | Conversation history, archival knowledge, persistent facts |

```{autodoc2-object} pynydus.api.schemas.MemoryLabel
```

### SourceType

Supported framework identifiers for SOURCE directives.

```{autodoc2-object} pynydus.api.schemas.SourceType
```

### Other enums

```{autodoc2-object} pynydus.api.schemas.Bucket
```

```{autodoc2-object} pynydus.api.schemas.RedactMode
```

```{autodoc2-object} pynydus.api.schemas.SecretKind
```

```{autodoc2-object} pynydus.api.schemas.InjectionMode
```

```{autodoc2-object} pynydus.api.schemas.PriorityHint
```
