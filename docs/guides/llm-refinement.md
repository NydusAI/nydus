# LLM Refinement

PyNydus optionally uses LLM calls during both spawning and hatching. Refinement
requires **`NYDUS_LLM_TYPE`** (`provider/model`) and **`NYDUS_LLM_API_KEY`**
together. If both are unset, refinement is skipped. If only one is set,
`load_config()` raises `ValueError` when it is invoked (SDK `Nydus()` and CLI
commands that load config, such as `spawn` and `hatch`). CLI commands that never
call `load_config()` are unaffected.

See {doc}`/guides/configuration` for all environment variables.

## During spawn (Step 7)


Two refinement passes run if LLM config is available and modules are non-empty:

### Skill cleanup

The LLM receives all skill records as JSON (id, name, content) and is prompted
to:

1. Normalize skill names (casing, remove redundant prefixes/suffixes).
2. Fix formatting (whitespace, heading levels, code block fencing).
3. Return exactly one output per input skill (1:1, no merging).
4. Preserve placeholder tokens exactly.

The response is a structured `RefinedSkillsOutput`: one `RefinedSkillRecord`
per input skill. Unknown IDs in the output are skipped.

### Memory deduplication

The LLM receives all memory records as JSON (id, text, label) and is prompted
to:

1. Identify duplicate or near-duplicate records and merge them.
2. Combine records that convey overlapping information.
3. Summarize verbose records while preserving factual content.
4. Preserve labels and placeholder tokens exactly.
5. List all original IDs for merged records (for audit trail).

The response is a structured `RefinedMemoryOutput` (via Instructor): a list
of records, each with `original_ids`, `text`, and `label`. Records with
multiple `original_ids` are merges. The output count may be less than or
equal to the input count.

If the LLM returns unknown record IDs, those entries are skipped with a warning.

### Fallback

If either LLM call fails (network error, invalid response, timeout), the
unrefined content is used. No error is raised. The `llm_call` log entry
captures the failure details.


The LLM always operates on already-redacted content. It never sees real PII or
secrets.

## During hatch (Step 3)


After the connector renders files (Step 2), the LLM optionally polishes or
adapts them:

- **Cross-platform hatch** (source != target): adapts tone, structure, and
  formatting for the target platform's conventions.

- **Same-platform hatch** (source = target): polishes formatting and improves
  clarity without changing meaning.


Runs **before** secret substitution (Step 4), so the LLM only sees
`{{SECRET_NNN}}` / `{{PII_NNN}}` placeholders.

### Prompt assembly

The hatch LLM prompt is assembled from five components:

1. **System prompt**: the adaptation prompt (cross-platform) or polish prompt
   (same-platform), with `AGENT_SPEC.md` content for source and target
   platforms injected inline.

2. **Spawn log**: the full JSON-serialized spawn log from the Egg, providing
   complete context about what happened during spawning.

3. **Redaction placeholders**: a listing of all secret/PII placeholders in the
   Egg with their kind and description.

4. **Original source files**: the redacted `raw/` snapshot, so the LLM can
   compare against the mechanically reconstructed output.

5. **Reconstructed files**: the file dict from the connector, formatted as
   `--- filename ---\ncontent\n`.

### Cross-platform system prompt

```text
You are a cross-platform adaptation engine for an AI agent migration system.
An agent was originally built for {source_type} and has been mechanically
reconstructed for {target_type}.
Your task is to adapt the generated files so they follow the idiomatic
conventions and best practices of the target platform.

Source platform specification:
{source_spec}

Target platform specification:
{target_spec}

Adaptation rules:
1. Adjust tone and structure to match target platform idioms.
2. Do NOT alter factual content or the agent's personality/knowledge.
3. Do NOT modify secret placeholders like {{SECRET_001}} or {{PII_001}}.
4. Only return files that you actually changed. If a file needs no adaptation, omit it.
```

### Same-platform polish prompt

```text
You are a polishing engine for an AI agent migration system.
An agent built for {target_type} has been reconstructed for the same platform.
Your task is to polish and improve the generated files so they follow the
idiomatic conventions and best practices of {target_type}.

Platform specification:
{target_spec}

Polishing rules:
1. Fix formatting inconsistencies: normalize headings, whitespace, and structure.
2. Improve clarity and readability without changing meaning.
3. Ensure the output follows {target_type} conventions precisely.
4. Do NOT alter factual content or the agent's personality/knowledge.
5. Do NOT modify secret placeholders like {{SECRET_001}} or {{PII_001}}.
6. Only return files that you actually changed. If a file needs no polishing, omit it.
```

### Response format

The LLM returns a structured `AdaptedFilesOutput`:

- `files`: list of `AdaptedFile` (path, content) for files that were changed.
- `warnings`: list of advisory messages about adaptation issues.

Files not returned by the LLM are kept unchanged. If the LLM returns a path
that does not exist in the file dict, it is dropped with a warning.

### Fallback

If the LLM call fails, the original file dict is returned unchanged. No error
is raised.

## Platform specifications (AGENT_SPEC.md)


Each platform connector directory contains an `AGENT_SPEC.md` file that
describes the platform's workspace conventions, file layout, and formatting
rules. At hatch time, Nydus loads the spec for both the source and target
platforms and injects them into the LLM prompt.

For cross-platform hatching, the LLM receives both specs so it can understand
the source conventions and adapt content to the target idioms. For same-platform
polishing, only the target spec is provided.

The specs live at `pynydus/agents/<platform>/AGENT_SPEC.md` and can be updated
as platform conventions evolve.

## Spawn log as context


The spawn pipeline records structured events at every step into `spawn_log`.
At hatch time, the **full JSON-serialized log** is injected into the hatch LLM
prompt so the model has complete context about what happened during spawning.

The log includes entries for every pipeline action:

| Event type | What it captures |
|------------|-----------------|
| `pipeline_start` | Source platform, base egg ref, redact flag, source paths |
| `source_files_read` | Agent type, resolved path, filenames, file count |
| `secret_scan` | Gitleaks finding: placeholder, rule name, source file |
| `redaction` | Presidio finding: PII type, placeholder, source file |
| `files_removed` | Glob patterns applied, files removed, remaining count |
| `spawner_parse` | Per-group skills/memory summaries, source metadata |
| `records_built` | Skill IDs/names, memory IDs/labels/text lengths |
| `base_egg_loaded` | Base egg ref, agent type, skill/memory/secret counts |
| `base_merge` | Before/after counts for skills, memory, secrets |
| `label_override` | Custom label changes: record ID, old/new label, pattern |
| `memory_excluded` | Dropped records by label, kept count |
| `memory_refined` | Per-record text changes (lengths, not content) |
| `memory_merge` | Merged record IDs, result length |
| `memory_refinement_done` | Total records processed, merged, unchanged |
| `skill_refined` | Name/content change flags per skill |
| `skill_refinement_done` | Total skills processed, changed count |
| `llm_call` | Provider, model, latency, token usage |
| `warning` | Warning messages from LLM refinement |
| `egg_packaged` | Final counts for skills, memory, secrets |
| `apm_passthrough` | APM yml stashed from source files |
| `a2a_passthrough` | A2A agent card copied from source |
| `a2a_generated` | A2A agent card generated from egg data |
| `agents_md_generated` | Per-egg AGENTS.md generated |
| `specs_embedded` | Spec snapshots embedded in egg |

No secret values or PII appear in the spawn log. Secret entries log only the
placeholder name and gitleaks rule ID. PII entries log only the entity type
and placeholder. Text content is logged as lengths, never as raw text.
