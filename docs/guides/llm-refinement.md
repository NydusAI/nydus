# LLM Refinement

PyNydus optionally uses LLM calls during both spawning and hatching. Refinement
requires **`NYDUS_LLM_TYPE`** (`provider/model`) and **`NYDUS_LLM_API_KEY`**
together. If both are unset, refinement is skipped. If only one is set,
`load_config()` raises `ValueError`.

See {doc}`/guides/configuration` for all environment variables.

## During spawn


- **Memory deduplication**: merges near-duplicate records, summarizes verbose
  entries, preserves labels and placeholders.

- **Skill cleanup**: normalizes names, fixes formatting, ensures proper markdown
  and code fencing.


The LLM always operates on already-redacted content. It never sees real PII or
secrets.

## During hatch


- **Cross-platform hatch** (source != target): adapts tone, structure, and
  formatting for the target platform's conventions.

- **Same-platform hatch** (source = target): polishes formatting and improves
  clarity without changing meaning.


Runs **before** secret substitution, so the LLM only sees
`{{SECRET_NNN}}` / `{{PII_NNN}}` placeholders.

## Spawn log as context


The spawn pipeline records events (redactions, classifications, LLM calls) in
`spawn_log.json`. At hatch time, that log is summarized and injected into the
hatch-side LLM prompt so the model can adapt output calibrated to real
spawn-time history.

| Event type | Example |
|------------|---------|
| `secret_scan` | API key detected, replaced with `{{SECRET_NNN}}` |
| `redaction` | 3 PII redactions (2 PERSON, 1 EMAIL_ADDRESS) |
| `classification` | 5 auto-classifications (3 persona, 2 flow) |
| `extraction` | 4 value extractions (2 skill, 2 memory) |
| `llm_call` | 2 LLM calls (450ms total) |
| `warning` | Pipeline warnings |
