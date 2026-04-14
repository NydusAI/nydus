# Spawn Pipeline

The spawn pipeline reads source agent files, redacts secrets and PII, parses
the platform-specific layout into structured records, and packages everything
into a portable Egg.

Entry point: `pynydus.engine.pipeline.spawn()`. Returns `(egg, raw_artifacts, logs)`.

## Pipeline context

Before any step runs, the Nydusfile is consumed into a `PipelineContext` that
front-loads all directive values (sources, base egg, redact flag, merge ops,
custom labels, excluded labels, remove globs). No step reads the Nydusfile
directly after this point.

A `spawn_log` list is attached to the context. Every step appends structured
entries to it. The log is stored in the Egg and forwarded to the hatch LLM
as full JSON context. See {doc}`/guides/llm-refinement` for all event types.

## Step 1: Resolve base egg

**Trigger:** `FROM` directive in the Nydusfile.

If a `FROM` reference is present, the pipeline loads the base egg and applies
any `ADD`, `SET`, or `REMOVE` merge operations to produce an `EggPartial`
(skills, memory, secrets, source metadata).

- **Local paths** (`FROM ./base.egg`) are resolved relative to the Nydusfile
  directory.
- **Registry references** (e.g. `FROM nydus/openclaw:0.3.0` as an illustrative
  tag) are pulled from the Nest registry into a temp file, then loaded. Use the
  `name:version` your server actually publishes.

If `FROM` is present but no `SOURCE`, the pipeline short-circuits: it applies
post-processing (custom labels, memory exclusions) to the base partial and
returns it directly as the Egg. No source files are read or scanned.

**Log entry:** `base_egg_loaded` (ref, agent type, module counts).

## Step 2: Read source files

**Trigger:** `SOURCE` directive in the Nydusfile (at most one).

The pipeline resolves the source path, instantiates the platform spawner, and
reads all files matching the spawner's `FILE_PATTERNS` glob list.

Files are read into a `dict[str, str]` (filename -> content). Subdirectory
patterns like `tools/*.py` are supported. Binary files that fail UTF-8 decode
are silently skipped.

If `REMOVE file <glob>` patterns are present, matching files are dropped from
the dict before any scanning or parsing.

**Log entries:** `source_files_read` (agent type, path, filenames, count),
optionally `files_removed` (patterns, removed filenames, remaining count).

## Step 3: Redaction

**Trigger:** `REDACT true` (the default).

This is the **secrets OUT boundary**. After this step, no real credentials
or PII exist anywhere in the pipeline. Everything downstream (spawner, LLM,
Egg archive) only sees `{{SECRET_NNN}}` and `{{PII_NNN}}` placeholders.

Redaction runs in two passes on the in-memory file dict:

### Pass 1: Gitleaks (credentials)

Scannable files (non-binary, as classified by extension) are written to a
temporary directory. Gitleaks runs against this temp dir and reports findings.
Each finding is replaced with a `{{SECRET_NNN}}` placeholder, producing a
`SecretRecord` with `kind=credential`.

Binary files (images, archives, executables, fonts, media) are passed through
unchanged. The full ignore list is defined in `pynydus.common.scan_paths.IGNORED_EXTENSIONS`.

**Log entry per finding:** `secret_scan` (tool, source file, placeholder, name).

### Pass 2: Presidio (PII)

The already-gitleaks-processed files are scanned by Microsoft Presidio for PII.
Detections above the confidence threshold (0.40) are replaced with
`{{PII_NNN}}` placeholders, producing `SecretRecord` entries with `kind=pii`.

Suppressed entity types (too noisy): `URL`, `DATE_TIME`, `NRP`.

Overlapping detections are resolved by keeping the higher-scoring, longer match.
Repeated identical values reuse the same placeholder across files.

**Log entry per finding:** `redaction` (source file, PII type, placeholder).

See {doc}`/guides/security` for the full list of detected entity types and
custom recognizers.

## Step 4: Parse sources

The platform spawner's `parse(files)` method receives the redacted file dict
(bare filename keys, placeholder'd content). It returns a `ParseResult`:

- `skills`: list of `RawSkill` (name, content, source_file)
- `memory`: list of `RawMemory` (text, label, source_file, timestamp)
- `mcp_configs`: dict of MCP server configurations (raw, Claude Desktop format)
- Neutral fields: `agent_name`, `agent_description`, `llm_model`, etc.

The spawner never sees real secrets. It operates entirely on placeholder tokens.

**Log entry:** `spawner_parse` (agent type, per-skill and per-memory summaries,
source metadata).

## Step 5: Build structured records

Raw spawner output is normalized into Pydantic records with stable IDs:

- `RawSkill` -> `AgentSkill` (with `metadata.id`=`skill_001`, `skill_002`, ...)
- `RawMemory` -> `MemoryRecord` (id=`mem_001`, `mem_002`, ...)
- Gitleaks + Presidio findings -> `SecretRecord` (deduplicated by placeholder)

Memory records that the spawner did not label default to `state`.

**Log entry:** `records_built` (skill IDs/names, memory IDs/labels/text lengths).

## Step 6: Merge with base egg

**Trigger:** Both `FROM` and `SOURCE` are present.

The base egg's modules (from Step 1) are combined with the freshly extracted
modules (from Step 5):

- **Skills**: concatenated, then re-numbered (`skill_001`, ...).
- **Memory**: concatenated, then re-numbered (`mem_001`, ...).
- **Secrets**: concatenated, deduplicated by name, then re-numbered.
- **MCP configs**: merged by server name (source overrides base).

If no `FROM` was present, this step is a no-op.

**Log entry:** `base_merge` (before/after counts for skills, memory, secrets).

## Step 7: LLM refinement (optional)

**Trigger:** `NYDUS_LLM_TYPE` and `NYDUS_LLM_API_KEY` are both set.

If LLM config is available and modules are non-empty, two refinement passes run:

- **Skill cleanup**: normalizes names, fixes formatting, ensures proper code
  fencing. One LLM call per batch. 1:1 mapping (no merging).
- **Memory deduplication**: merges near-duplicate records, summarizes verbose
  entries, preserves labels and placeholders. May reduce record count.

Both operate on already-redacted content. The LLM never sees real secrets.
If the LLM call fails, the unrefined content is used without error.

See {doc}`/guides/llm-refinement` for prompt details and response format.

**Log entries:** `skill_refined`, `skill_refinement_done`, `memory_refined`,
`memory_merge`, `memory_refinement_done`, `llm_call`.

## Step 8: Post-processing

Two Nydusfile directives are applied after refinement:

### LABEL overrides

`LABEL <pattern> <label>` directives override the memory label on records
whose `source_store` matches the glob pattern. Labels must be one of
`persona`, `flow`, `context`, `state`. The first matching pattern wins.

**Log entry:** `label_override` (record ID, old label, new label, pattern).

### EXCLUDE

`EXCLUDE <label>` directives drop all memory records with the given label.
Source files are still preserved in the archive's `raw/` snapshot. Only structured memory records
are removed.

**Log entry:** `memory_excluded` (excluded labels, dropped record details,
kept count).

## Step 9: Package egg

The final `Egg` is constructed from:

- **Manifest**: nydus version, min version, egg spec version, timestamp,
  agent type, neutral fields (agent name, LLM model, etc.), redaction policy, base egg ref.
- **SkillsModule**: all `AgentSkill` records (agentskills.io format).
- **McpModule**: raw MCP server configs (Claude Desktop format).
- **MemoryModule**: all memory records (post-label, post-exclude).
- **SecretsModule**: all secret/PII placeholder records.

The redacted source files (from Step 3) become `raw_artifacts`, stored as
`raw/` in the `.egg` archive for passthrough hatching.

**Log entry:** `egg_packaged` (agent type, final skill/memory/secret counts).

## Step 10: Generate standard artifacts

Standard artifacts are generated and attached to the egg:

- **APM**: if `apm.yml` exists in source files, it's stashed as `egg.apm_yml`.
- **A2A**: if `agent-card.json` exists, passthrough; otherwise generated from egg data.
- **AGENTS.md**: deployment runbook generated from egg contents.
- **Specs**: all spec markdown files embedded as `egg.spec_snapshots`.

**Log entries:** `apm_passthrough`, `a2a_generated` / `a2a_passthrough`,
`agents_md_generated`, `specs_embedded`.
