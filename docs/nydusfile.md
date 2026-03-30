# Nydusfile DSL

The Nydusfile is a declarative, statically verifiable DSL for controlling
spawning. It has no conditionals, no loops, and no side effects. Every
directive can be verified before execution.

## Grammar

```text
Nydusfile := Directive*
Directive := FROM | SOURCE | INCLUDE | EXCLUDE | REDACT
           | PRIORITIZE | PURPOSE | ADD | SET | REMOVE
           | EXCLUDE_FILES | LABEL | SECRET_POLICY
```

## Example

```text
FROM nydus/openclaw:0.2.0
SOURCE openclaw ./my-agent/
INCLUDE skills, memory
REDACT pii
ADD skill ./custom-summarizer/
ADD memory "Working on Project X with Snowflake"
ADD secret SNOWFLAKE_API_KEY
SET memory.label=persona "Prefers responses in Korean"
REMOVE skill outdated-workflow
PRIORITIZE compact_memory
PURPOSE "multilingual data engineering assistant"
```

## Directives reference

### FROM

```text
FROM <egg-reference>
```

Versioned base egg from the Nest registry or a local `.egg` file path. The base
egg's contents are used as the starting point. ADD/SET/REMOVE modify it.

Only accepts egg references, not source types. Use SOURCE instead of
`FROM openclaw`.

Examples:
- `FROM nydus/openclaw:0.2.0`
- `FROM ./base.egg`

### SOURCE

```text
SOURCE <source_type> <path>
```

Repeatable. Declares an input source. Each source is processed by its
corresponding spawner. Multiple SOURCE directives produce a pooled extraction.

Source types: `openclaw`, `zeroclaw`, `letta`.

### INCLUDE / EXCLUDE

```text
INCLUDE <bucket-list>
EXCLUDE <bucket-list>
```

Control which module buckets appear in the Egg. Bucket names: `skills`,
`memory`, `secrets`. A bucket cannot appear in both INCLUDE and EXCLUDE.

### REDACT

```text
REDACT <mode>
```

Redaction mode: `pii` (default), `secrets`, `all`, `none`. When `none`, a
warning is logged.

### ADD

```text
ADD <bucket> <content-or-path>
ADD <bucket> "<inline text>"
```

Add content to a bucket. For skills and memory, accepts a file path or a quoted
inline string. For secrets, accepts a secret name.

Examples:
- `ADD skill ./custom-summarizer/`
- `ADD memory "Working on Project X"`
- `ADD secret SNOWFLAKE_API_KEY`

### SET

```text
SET <bucket>.<selector> "<value>"
```

Override or add a labeled record. The selector identifies which records to
modify.

Example: `SET memory.label=persona "Prefers concise responses"`

### REMOVE

```text
REMOVE <bucket> <identifier>
```

Remove a named record inherited from the base egg.

Example: `REMOVE skill outdated-workflow`

### PRIORITIZE

```text
PRIORITIZE <hint>
```

Repeatable. Soft hints for the pipeline: `recent_history`, `skills`,
`compact_memory`.

### PURPOSE

```text
PURPOSE "<quoted string>"
```

Human-provided build intent. Stored in `manifest.build_intent` and used by the
LLM as context during refinement.

### EXCLUDE_FILES

```text
EXCLUDE_FILES <glob-pattern>
```

Repeatable. Glob patterns for files to skip during source extraction.

### LABEL

```text
LABEL <pattern> <label>
```

Repeatable. Override memory record labels based on source file pattern matching.

Example: `LABEL soul.md persona`

### SECRET_POLICY

```text
SECRET_POLICY <policy>
```

Controls `required_at_hatch` on all secrets: `all_required`, `none_required`,
or `default`.

## Static verification

The parser performs these checks before execution:

| Check | Description |
|-------|-------------|
| FROM resolves | Base egg exists (local path or registry reference) |
| SOURCE types valid | Each SOURCE references a known spawner |
| No bucket contradictions | A bucket is not both INCLUDEd and EXCLUDEd |
| ADD targets valid bucket | References `skill`, `memory`, or `secret` |
| PII safety warning | Warning if REDACT is `none` |
| Merge ops require base | ADD/SET/REMOVE require a FROM base egg |
| At least one input | Nydusfile must have FROM or at least one SOURCE |
