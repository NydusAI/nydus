# Nydusfile DSL

The Nydusfile is a declarative, statically verifiable DSL for controlling
spawning. It has no conditionals, no loops, and no side effects. Every
directive can be verified before execution.

## Grammar

```text
Nydusfile := Directive*
Directive := FROM | SOURCE | REDACT | EXCLUDE
           | LABEL | ADD | SET | REMOVE
```

## Example

```text
FROM nydus/openclaw:0.3.0
SOURCE openclaw ./my-agent/
REDACT true
ADD skill ./custom-summarizer/
ADD memory "Working on Project X with Snowflake"
ADD secret SNOWFLAKE_API_KEY
SET memory.label=persona "Prefers responses in Korean"
REMOVE skill outdated-workflow
REMOVE file *.log
EXCLUDE state
LABEL soul.md persona
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

> **Note:** When both FROM and SOURCE are present, FROM provides the base
> template and SOURCE supplies fresh source extraction. Base egg records are
> merged with the extracted records. ADD/SET/REMOVE modify the base egg
> **before** merging.

Examples:
- `FROM nydus/openclaw:0.3.0`
- `FROM ./base.egg`

### SOURCE

```text
SOURCE <agent_type> <path>
```

Declares a single input source (at most **one** `SOURCE` line per Nydusfile).
The tree at `<path>` is processed by the corresponding spawner. To combine
several agent layouts, merge them under one directory or use separate Nydusfiles.

Source types: `openclaw`, `zeroclaw`, `letta`.

### REDACT

```text
REDACT true|false
```

Enable or disable secret scanning (gitleaks) and PII redaction (Presidio).

If the `REDACT` directive is **omitted**, redaction defaults to **`true`** (same
as `REDACT true`). When `REDACT false` is set, a warning is logged and all real
values remain in the Egg.

### EXCLUDE

```text
EXCLUDE <memory-label>
```

Repeatable. Each line names a **memory bucket** to omit from the final Egg:
`persona`, `flow`, `context`, or `state` (same vocabulary as `LABEL`). Matching
is case-insensitive on the label token.

After the spawner builds memory and any `LABEL` overrides are applied, every
`MemoryRecord` whose label is listed is **removed** from `Egg.memory`. Source
files are still read and appear in `raw/` snapshots; only structured memory for
those buckets is dropped. **Skills** are not affected.

**Breaking change:** Older Nydusfiles that used `EXCLUDE` with file glob
patterns must be updated to memory labels (or use another mechanism for file
filtering if added later).

### LABEL

```text
LABEL <pattern> <label>
```

Repeatable. Override memory record labels based on source file pattern matching.
The label must be one of: `persona`, `flow`, `context`, `state`. Duplicate
patterns are rejected at parse time.

Example: `LABEL soul.md persona`

### ADD

```text
ADD <bucket> <content-or-path>
ADD <bucket> "<inline text>"
```

Add content to a bucket. For skills and memory, accepts a file path or a quoted
inline string. For secrets, accepts a secret name. Bucket names: `skill`,
`memory`, `secret`.

Examples:
- `ADD skill ./custom-summarizer/`
- `ADD memory "Working on Project X"`
- `ADD secret SNOWFLAKE_API_KEY`

### SET

```text
SET <bucket>.<selector> "<value>"
```

Override all records matching the selector in the `memory` or `skill` bucket.
Not supported for `secret` — use REMOVE + ADD instead. All matching records are
updated (not just the first).

Example: `SET memory.label=persona "Prefers concise responses"`

### REMOVE

Two forms:

**1. Merger (requires `FROM`)** — mutate the base egg before any `SOURCE` merge:

```text
REMOVE <bucket> <identifier>
```

Remove a named record inherited from the base egg.

Example: `REMOVE skill outdated-workflow`

**2. Source file drop (requires `SOURCE`)** — omit files from extraction, parse, and `raw/`:

```text
REMOVE file <glob-pattern>
```

Repeatable. Glob patterns match **source file keys** (e.g. `soul.md`, `skills/*.md`), like shell `fnmatch`. Applied after read, before redaction and parse.

Example: `REMOVE file *.log`

Merger-style `REMOVE skill …` and `REMOVE file …` can appear in the same Nydusfile when both `FROM` and `SOURCE` are set.

## Auto-generated Nydusfile

If no `Nydusfile` exists in the project directory, commands such as `nydus spawn`
may create one from a template after **auto-detecting** the agent layout. If
**multiple** agent types match the same directory (e.g. OpenClaw and ZeroClaw
both recognize common files), detection is **ambiguous** — add a `Nydusfile`
yourself with an explicit `SOURCE <agent_type> <path>` line.

## Static verification

The parser performs these checks before execution:

| Check | When | Description |
|-------|------|-------------|
| FROM shape valid | Parse | Value is not a bare source type |
| FROM resolves | Spawn | Base egg exists (local path or registry pull) |
| SOURCE types valid | Parse | `SOURCE` references a known spawner; at most one `SOURCE` line |
| ADD/SET target valid bucket | Parse | References `skill`, `memory`, or `secret` (SET: `skill` or `memory` only) |
| LABEL value valid | Parse | Label must be a known MemoryLabel (`persona`, `flow`, `context`, `state`) |
| LABEL pattern unique | Parse | Same pattern cannot be assigned two different labels |
| PII safety warning | Parse | Warning if REDACT is `false` |
| Merge ops require base | Parse | ADD/SET/REMOVE (merger form) require a FROM base egg |
| `REMOVE file` requires SOURCE | Parse | File drops apply only when a `SOURCE` tree is read |
| At least one input | Parse | Nydusfile must have FROM or at least one SOURCE |
