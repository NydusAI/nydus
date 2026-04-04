# Pipelines

PyNydus has two core pipelines: **spawn** (source → Egg) and **hatch**
(Egg → target). Both enforce a strict secrets boundary — the LLM and
connectors never see real credential or PII values.

```text
Source artifacts → Spawn → Egg (.egg) → Hatch → Target-native files
```

## Spawn pipeline

The spawn pipeline lives in `pynydus.engine.pipeline.spawn()`. It returns
`(egg, raw_artifacts, logs)`.

### Phase 1: Parse Nydusfile

Resolves source type from the Nydusfile. If `FROM` is set, loads the
base egg and applies merge operations.

When no Nydusfile exists yet, PyNydus may generate one by probing each spawner’s
`detect()` on the current directory. If **more than one** agent type matches
(e.g. overlapping OpenClaw and ZeroClaw layouts), spawn fails with an
**ambiguous layout** error until you add an explicit `SOURCE <type> <path>` line.

### Phase 2: Read source files

The spawner's `FILE_PATTERNS` list determines which files are read from the
source directory into an in-memory `dict[str, str]`. Immediately afterward,
`REMOVE file <glob>` patterns (if any) **drop** matching keys from that dict
before secret scan. There is no file-level `EXCLUDE`; the `EXCLUDE` directive
drops memory **buckets** after records are built (see Phase 8).

### Phase 3: Secret scan — gitleaks (secrets OUT boundary, part 1)

When `REDACT true` (the default) is set, files are classified by extension
(binary files are skipped) and written to a temp directory. The external
**gitleaks** CLI scans for secrets (API keys, tokens, passwords) and replaces
matched values with `{{SECRET_NNN}}` placeholders. A `SecretRecord` of kind
`credential` is created for each finding.

Gitleaks must be installed when spawning with `REDACT true` and `SOURCE`
directives. The pipeline raises `GitleaksNotFoundError` before starting if the
binary is missing.

### Phase 4: PII redaction — Presidio (secrets OUT boundary, part 2)

When `REDACT true` (the default), a Presidio-based `PIIRedactor` scans all
(now secret-free) file contents for PII, replacing detected entities with
`{{PII_NNN}}` placeholders and creating `SecretRecord` entries of kind `pii`.
After this phase, file contents contain only placeholders. No real secrets or
PII remain.

See {doc}`advanced/pii-redaction` for details on the gitleaks and Presidio
integration.

### Phase 5: Parse

The spawner's `parse(files)` method receives the fully redacted file contents
and produces a `ParseResult` with `RawSkill` and `RawMemory` lists. The spawner
never sees real credentials or PII.

### Phase 6: Build records

Raw skills and memory become `SkillRecord` and `MemoryRecord` lists with stable
IDs (`skill_001`, `mem_001`, ...). Credential and PII secrets from phases 3–4
are merged and deduplicated into a `SecretsModule`.

### Phase 7: LLM refinement

If LLM refinement is configured, the configured model cleans skill formatting and
deduplicates/summarizes memory. The LLM always operates on already-redacted
content. It never sees raw PII or secrets.

See {doc}`advanced/llm-refinement` for configuration and details.

### Phase 8: Filter + Package

Applies custom label overrides (`LABEL`), then removes any `MemoryRecord` whose
label appears in `EXCLUDE` (see {doc}`nydusfile` §EXCLUDE).
Finally assembles the final `Egg` with a populated manifest.

## Hatch pipeline

The hatch pipeline lives in `pynydus.engine.hatcher.hatch()`.

### Phase 1: Compatibility check

Verifies the egg's version requirements against the installed PyNydus version.

### Phase 2: Hatch mode — rebuild (default) or passthrough

Hatching uses exactly one of two modes:

- **rebuild** (default): build output from structured egg modules. The
  target-specific hatcher's `render(egg)` produces an in-memory `dict[str, str]`
  with `{{SECRET_NNN}}` and `{{PII_NNN}}` placeholders intact. The hatcher never
  touches real secret values.
- **passthrough** (CLI `--passthrough`): replay the redacted `raw/` snapshot from the
  archive verbatim. Requires the hatch `--target` to match the egg's source type
  and a non-empty `raw/` layer; otherwise the command fails with a clear error.

For LLM refinement, `raw/` may still be loaded and passed as context in
**rebuild** mode even though output files come from `render(egg)`.

### Phase 3: LLM refinement

If LLM is configured, the same tier adapts the in-memory file contents
while they still contain only `{{SECRET_NNN}}` / `{{PII_NNN}}` placeholders —
the LLM never sees real secret values:

- **Cross-platform hatch** (source ≠ target): adapts tone and structure for the
  target platform's conventions.
- **Same-platform hatch** (source = target): polishes formatting and improves
  clarity without changing meaning.

The LLM receives the file contents, the egg's secrets summary, the raw source
artifacts (if available), and the spawn log for full context.

See {doc}`advanced/llm-refinement` for configuration and the encoder–decoder
analogy.

### Phase 4: Secret substitution (secrets IN boundary)

If a `.env` file is provided via `--secrets`, placeholders are resolved: the
egg's secret names are matched to environment variable names, and values are
substituted in the in-memory file contents. Missing required secrets raise an
error. This is the last transformation before writing to disk.

### Phase 5: Write files

The final file contents are written to the output directory on disk.

### Phase 6: Write hatch log

Writes `hatch_log.json` to `output_dir/logs/`.
