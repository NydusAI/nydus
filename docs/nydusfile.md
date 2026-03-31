# Nydusfile DSL

The Nydusfile is a declarative configuration file that controls how Eggs are
built. It has no conditionals, no loops, and no side effects. Every directive
can be validated before execution.

Place a file named `Nydusfile` (no extension) in your working directory.

## Grammar

```text
Nydusfile := Directive*
Directive := FROM | SOURCE | INCLUDE | EXCLUDE | REDACT
           | PRIORITIZE | PURPOSE | ADD | SET | REMOVE
           | EXCLUDE_FILES | LABEL | SECRET_POLICY
```

Each directive occupies one line. Blank lines and trailing whitespace are
ignored.

## Practical examples

### Minimal

The simplest Nydusfile points at one source directory:

```text
SOURCE openclaw ./my-agent/
REDACT pii
```

### Multi-source

Combine inputs from multiple frameworks into one Egg:

```text
SOURCE openclaw ./agent-a/
SOURCE letta ./agent-b/
REDACT pii
PURPOSE "multilingual support assistant"
```

Records from all sources are pooled and merged.

### Layering on a base Egg

Start from a published Egg and add or override content:

```text
FROM nydus/openclaw:0.2.0
ADD skill ./custom-summarizer/
ADD memory "Working on Project X with Snowflake"
ADD secret SNOWFLAKE_API_KEY
SET memory.label=persona "Prefers responses in Korean"
REMOVE skill outdated-workflow
```

`FROM` pulls the base from the Nest registry (or a local `.egg` path).
`ADD`, `SET`, and `REMOVE` modify the base content.

### Filtering

Control which modules appear in the output and which source files to skip:

```text
SOURCE openclaw ./my-agent/
INCLUDE skills, memory
EXCLUDE secrets
EXCLUDE_FILES *.log
EXCLUDE_FILES drafts/**
REDACT pii
```

### Label overrides

Override the automatic label assigned to a source file:

```text
SOURCE zeroclaw ./my-agent/
LABEL soul.md persona
LABEL notes.md state
REDACT pii
```

### Secret policy

Control whether secrets are required at hatch time:

```text
SOURCE openclaw ./my-agent/
REDACT secrets
SECRET_POLICY all_required
```

## Directives reference

### FROM

```text
FROM <egg-reference>
```

Versioned base Egg from the Nest registry or a local `.egg` file path. The base
Egg's contents are used as the starting point. `ADD`, `SET`, and `REMOVE`
directives modify it.

Only accepts Egg references, not source types. Use `SOURCE` for reading live
agent directories.

- `FROM nydus/openclaw:0.2.0` (registry reference)
- `FROM ./base.egg` (local file)

### SOURCE

```text
SOURCE <source_type> <path>
```

Repeatable. Declares an input source directory or file. Each source is processed
by its framework-specific spawner. Multiple `SOURCE` directives produce a pooled
extraction.

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

Redaction mode applied before content parsing:

| Mode | Behavior |
|------|----------|
| `pii` | Credential scanning plus PII entity detection (default) |
| `secrets` | Credential scanning only, no PII pass |
| `all` | Full combination of credential and PII handling |
| `none` | Skip redaction (warning logged, use only in trusted local contexts) |

### ADD

```text
ADD <bucket> <content-or-path>
ADD <bucket> "<inline text>"
```

Add content to a bucket. Requires a `FROM` base Egg.

- `ADD skill ./custom-summarizer/` (directory path)
- `ADD memory "Working on Project X"` (inline text)
- `ADD secret SNOWFLAKE_API_KEY` (secret name)

### SET

```text
SET <bucket>.<selector> "<value>"
```

Override or add a labeled record. The selector identifies which records to
modify.

- `SET memory.label=persona "Prefers concise responses"`

### REMOVE

```text
REMOVE <bucket> <identifier>
```

Remove a named record inherited from the base Egg.

- `REMOVE skill outdated-workflow`

### PRIORITIZE

```text
PRIORITIZE <hint>
```

Repeatable. Soft hints for the pipeline that influence refinement behavior.
Available hints: `recent_history`, `skills`, `compact_memory`.

### PURPOSE

```text
PURPOSE "<quoted string>"
```

Human-provided build intent. Stored in `manifest.build_intent` and used by
the LLM as context during optional refinement.

### EXCLUDE_FILES

```text
EXCLUDE_FILES <glob-pattern>
```

Repeatable. Glob patterns for source files to skip during extraction.

- `EXCLUDE_FILES *.log`
- `EXCLUDE_FILES drafts/**`

### LABEL

```text
LABEL <pattern> <label>
```

Repeatable. Override the memory label that the spawner assigns to files
matching the given pattern. Labels: `persona`, `flow`, `context`, `state`.

- `LABEL soul.md persona`
- `LABEL notes.md state`

### SECRET_POLICY

```text
SECRET_POLICY <policy>
```

Controls whether placeholders must be resolved at hatch time:

| Policy | Behavior |
|--------|----------|
| `default` | Each secret uses its own `required_at_hatch` setting |
| `all_required` | All secrets must be supplied in the `.env` file |
| `none_required` | Hatching proceeds even with unresolved placeholders |

## Static verification

The Nydusfile parser validates directives before execution:

| Check | What it catches |
|-------|-----------------|
| FROM resolves | Base Egg must exist (local path or registry reference) |
| SOURCE types valid | Each SOURCE references a known spawner (`openclaw`, `zeroclaw`, `letta`) |
| No bucket contradictions | A bucket cannot appear in both INCLUDE and EXCLUDE |
| ADD targets valid bucket | Must reference `skill`, `memory`, or `secret` |
| PII safety warning | Warning if REDACT is `none` |
| Merge ops require base | `ADD`, `SET`, `REMOVE` require a `FROM` base Egg |
| At least one input | Nydusfile must have `FROM` or at least one `SOURCE` |
