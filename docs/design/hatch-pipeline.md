# Hatch Pipeline

The hatch pipeline transforms an Egg into a target runtime's file layout.
It renders structured modules into platform-specific files, optionally
polishes them via LLM, injects real secret values, and writes everything
to disk.

Entry point: `pynydus.engine.hatcher.hatch()`. Returns a `HatchResult`.

## Hatch modes

The pipeline supports two modes, chosen at invocation:

**Rebuild** (default): The target connector's `render(egg)` method generates
files from the Egg's structured modules (skills, memory, secrets). This works
for both same-platform and cross-platform hatching. The output follows the
target platform's canonical layout.

**Passthrough** (`--passthrough`): The redacted `raw/` snapshot from the Egg
archive is replayed verbatim. No connector render step runs. Requires the
target type to match the source type and `raw/` to be non-empty. Useful when
the original file structure must be preserved exactly (minus real secret values,
which are injected in Step 4).

## Step 1: Version check

The pipeline reads `egg.manifest.min_nydus_version` and compares it against
the running PyNydus version. If the Egg requires a newer version, hatching
is rejected with a `HatchError` telling the user to upgrade.

This ensures forward compatibility: newer Eggs that use features unavailable
in older runtimes are not silently mishandled.

## Step 2: Build file dict

Depending on the mode:

### Rebuild

The target connector is instantiated via `_get_hatcher(target)` and its
`render(egg)` method is called. This returns a `RenderResult`:

- `files`: `dict[str, str]` of filename -> content (placeholders intact)
- `warnings`: list of advisory messages

Each connector implements platform-specific logic for mapping Egg modules
back to the target's file layout. See {doc}`/design/connectors` for the
full mapping tables.

**Log entry:** `render_from_modules` (source type, target type, skill/memory
counts, file count).

### Passthrough

The `raw_artifacts` dict (from `egg.raw_artifacts` or passed explicitly) is
used as the file dict. No connector runs.

Passthrough validates:
- Target type must equal source type (cross-platform passthrough is rejected).
- `raw_artifacts` must be non-empty (eggs loaded with `include_raw=False` have
  an empty dict).

**Log entry:** `raw_snapshot` (source type, target type, file count).

## Step 3: LLM polish

**Trigger:** LLM config is provided and the file dict is non-empty.

The pipeline calls `refine_hatch()`, which assembles an LLM prompt from:

1. **System prompt**: either the cross-platform adaptation prompt (source !=
   target) or the same-platform polish prompt. Both include the target
   `AGENT_SPEC.md` content. Cross-platform also includes the source spec.
2. **Spawn log**: the full JSON-serialized spawn log, so the LLM knows what
   happened during spawning (redaction counts, record structure, metadata).
3. **Redaction placeholders**: a listing of all `{{SECRET_NNN}}` / `{{PII_NNN}}`
   tokens in the Egg with their kind and description.
4. **Original source files**: the redacted `raw/` contents (if available), so
   the LLM can compare against the mechanically reconstructed output.
5. **Reconstructed files**: the file dict from Step 2, formatted as
   `--- filename ---\ncontent\n`.

The LLM returns an `AdaptedFilesOutput`: a list of `(path, content)` pairs
for files it changed, plus optional warnings. Files the LLM did not return
are kept unchanged. Unknown file paths in the LLM response are dropped with
a warning.

If the LLM call fails, the original file dict is returned unchanged.

All content at this point still contains placeholders. The LLM never sees
real secrets.

See {doc}`/guides/llm-refinement` for the full prompt templates and response
schemas.

**Log entries:** `llm_call` (from the LLM client), optionally `warning`
entries from the LLM response.

## Step 4: Secrets IN

This is the **secrets IN boundary**, the last transformation before writing
to disk. After this step, files contain real secret values.

The pipeline reads the `.env` file (if provided via `--secrets`), builds a
`placeholder -> real value` mapping from the Egg's `SecretRecord` entries,
and performs string substitution across all file contents.

The `.env` file format is standard key=value pairs:

```text
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=wJalr...
PII_PERSON=John Smith
```

Keys in the `.env` must match `SecretRecord.name`. If a record has
`required_at_hatch=True` and its name is missing from the `.env`, hatching
fails with a `HatchError` listing the missing secrets.

Use `nydus env agent.egg` to generate a template `.env` listing all secrets
the Egg needs.

**Log entry per substitution:** `secret_injection` (placeholder name).

## Step 5: Write to disk

All files in the dict are written to the output directory (default `./agent/`).
Parent directories are created as needed. The function returns a list of
created filenames.

## Step 6: Hatch log

The accumulated `hatch_log` entries are written to `logs/hatch_log.json`
inside the output directory. This provides an audit trail of what happened
during hatching: which mode was used, how many files were rendered, which
secrets were injected, and any LLM warnings.
