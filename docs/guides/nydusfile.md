# Nydusfile DSL

The Nydusfile is a declarative, statically verifiable DSL for controlling
spawning. No conditionals, no loops, no side effects.

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

Versioned base egg from the Nest registry or a local `.egg` path. The base
egg's contents are the starting point. ADD/SET/REMOVE modify it.

Only accepts egg references, not source types. Use SOURCE instead of
`FROM openclaw`.

> **Note:** When both FROM and SOURCE are present, FROM provides the base
> template and SOURCE supplies fresh extraction. ADD/SET/REMOVE modify the
> base egg **before** merging.

Examples:
- `FROM nydus/openclaw:0.3.0`
- `FROM ./base.egg`

### SOURCE

```text
SOURCE <agent_type> <path>
```

Declares a single input source (at most **one** per Nydusfile).
Source types: `openclaw`, `zeroclaw`, `letta`.

### REDACT

```text
REDACT true|false
```

Enable or disable secret scanning and PII redaction. Defaults to **`true`**
when omitted. See {doc}`security` for details.

### EXCLUDE

```text
EXCLUDE <memory-label>
```

Repeatable. Names a **memory bucket** to omit from the final Egg:
`persona`, `flow`, `context`, or `state`. Matching is case-insensitive.

Source files are still read and appear in `raw/`. Only structured memory
for those buckets is dropped. Skills are not affected.

### LABEL

```text
LABEL <pattern> <label>
```

Repeatable. Override memory record labels based on source file pattern.
Label must be one of: `persona`, `flow`, `context`, `state`. Duplicate
patterns are rejected at parse time.

### ADD

```text
ADD <bucket> <content-or-path>
ADD <bucket> "<inline text>"
```

Add content to a bucket (`skill`, `memory`, `secret`). Accepts a file path,
quoted inline string, or secret name.

### SET

```text
SET <bucket>.<selector> "<value>"
```

Override matching records in `memory` or `skill`. Not supported for `secret`
(use REMOVE + ADD instead). All matching records are updated.

### REMOVE

Two forms:

**Merger** (requires `FROM`). Mutates the base egg before SOURCE merge:

```text
REMOVE <bucket> <identifier>
```

**Source file drop** (requires `SOURCE`). Omits files from extraction:

```text
REMOVE file <glob-pattern>
```

Glob patterns match source file keys (e.g. `soul.md`, `skills/*.md`).
Applied after read, before redaction and parse.

## Auto-generated Nydusfile

If no `Nydusfile` exists, `nydus spawn` auto-detects the agent layout.
If **multiple** agent types match (ambiguous), add a `Nydusfile` with an
explicit `SOURCE <agent_type> <path>` line.

## Static verification

| Check | Description |
|-------|-------------|
| FROM shape valid | Value is not a bare source type |
| FROM resolves | Base egg exists (local or registry) |
| SOURCE types valid | Known spawner, at most one SOURCE |
| ADD/SET target valid | References `skill`, `memory`, or `secret` |
| LABEL value valid | Known MemoryLabel (`persona`, `flow`, `context`, `state`) |
| LABEL pattern unique | Same pattern cannot have two labels |
| PII safety warning | Warning if REDACT is `false` |
| Merge ops require base | ADD/SET/REMOVE (merger) require FROM |
| REMOVE file requires SOURCE | File drops need a SOURCE tree |
| At least one input | Must have FROM or SOURCE |
