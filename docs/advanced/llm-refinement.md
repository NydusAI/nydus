# LLM Refinement

PyNydus optionally uses LLM calls during both spawning and hatching. Refinement
requires **`NYDUS_LLM_TYPE`** (`provider/model`) and **`NYDUS_LLM_API_KEY`**
together. The same **provider**, **model**, and **api_key** are used for all
refinement steps.

There are no implicit defaults. If those env vars are unset, refinement is skipped.
See {doc}`../configuration`.

## Spawn-side (phase 7)

- **Memory deduplication**: merges near-duplicate records, summarizes verbose
  entries, preserves labels and placeholders.
- **Skill cleanup**: normalizes names, fixes formatting, ensures proper markdown
  and code fencing.

The LLM always operates on already-redacted content. It never sees real PII or
secrets.

## Hatch-side (phase 4)

- **Cross-platform hatch** (source ≠ target): adapts tone, structure, and
  formatting for the target platform's conventions.
- **Same-platform hatch** (source = target): polishes formatting and improves
  clarity without changing meaning.

Hatch-side refinement runs **before** secret substitution, so the LLM only ever
sees `{{SECRET_NNN}}` / `{{PII_NNN}}` placeholders — never real credentials or
PII. This mirrors the spawn side.

The LLM receives the reconstructed file contents (with placeholders), the egg's
secrets summary, the raw source artifacts (if available), and a summarized spawn
log.

## Why the hatch LLM sees the spawn log

In encoder–decoder models, the encoder builds a representation of the input so
the decoder can generate output that stays faithful to it. PyNydus follows a
similar **information-flow** pattern: it is not a single model's internal
attention weights, but the same idea—**upstream analysis conditions downstream
generation**.

The **spawn** pipeline records what happened (redactions, classifications,
extractions, spawn-side LLM usage, and more) in **`spawn_log.json`**. At
**hatch** time, that log is **summarized** and injected into the hatch-side LLM
prompt together with the reconstructed files, secrets summary, and optional
`raw/` text. The hatch model can then adapt or polish output in a way that is
**calibrated** to the real spawn-time history instead of inferring it from the
egg alone.

```text
Encoder–decoder (conceptual)     Encoder  →  [representation for the input]  →  Decoder  →  output

PyNydus (spawn → hatch LLM)      Spawn    →  spawn_log (trace, summarized)     →  Hatch LLM →  files
```

The spawn log records these event types:

| Event type | Example |
|------------|---------|
| `secret_scan` | `tool: "gitleaks"`, API key / token detected, replaced with `{{SECRET_NNN}}` |
| `redaction` | 3 PII redactions (2 PERSON, 1 EMAIL_ADDRESS) |
| `classification` | 5 auto-classifications (3 persona, 2 flow) |
| `extraction` | 4 value extractions (2 skill, 2 memory) |
| `llm_call` | 2 LLM calls (450ms total) |
| `warning` | pipeline warnings |

The summary is compact (a few lines) so it fits in the hatch LLM context
without overwhelming the prompt.
