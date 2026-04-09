# Data Models

Core Pydantic models for the Egg data structure. These types are all importable
from the top-level PyNydus package (`pynydus`).

## Egg

```{autodoc2-object} pynydus.api.schemas.Egg
```


## Manifest

```{autodoc2-object} pynydus.api.schemas.Manifest
```

```{autodoc2-object} pynydus.api.schemas.RedactionPolicy
```

```{autodoc2-object} pynydus.api.schemas.SourceEntry
```

## Module containers

```{autodoc2-object} pynydus.api.schemas.SkillsModule
```

```{autodoc2-object} pynydus.api.schemas.MemoryModule
```

```{autodoc2-object} pynydus.api.schemas.SecretsModule
```

## Records

```{autodoc2-object} pynydus.api.schemas.SkillRecord
```

```{autodoc2-object} pynydus.api.schemas.MemoryRecord
```

```{autodoc2-object} pynydus.api.schemas.SecretRecord
```

```{autodoc2-object} pynydus.api.schemas.McpServerConfig
```

## Pipeline results

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

```{autodoc2-object} pynydus.api.schemas.ManifestChange
```

```{autodoc2-object} pynydus.api.schemas.EggPartial
```

## Enums

These types are defined in `pynydus.common.enums` and re-exported from
`pynydus.api.schemas` for convenience.

```{autodoc2-object} pynydus.common.enums.AgentType
```

```{autodoc2-object} pynydus.common.enums.Bucket
```

```{autodoc2-object} pynydus.common.enums.SecretKind
```

```{autodoc2-object} pynydus.common.enums.InjectionMode
```

```{autodoc2-object} pynydus.common.enums.MemoryLabel
```

```{autodoc2-object} pynydus.common.enums.HatchMode
```

```{autodoc2-object} pynydus.common.enums.DiffChange
```

