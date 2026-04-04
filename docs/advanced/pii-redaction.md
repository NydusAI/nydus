# PII & Secret Redaction

Nydus uses two tools to sanitize source files before parsing:

- **Gitleaks** (external CLI) — scans for secrets: API keys, tokens, passwords,
  and other credential patterns.
- **Presidio** (Python library) — scans for PII: names, emails, phone numbers,
  SSNs, credit cards, and other personally identifiable information.

When `REDACT true` (the default) is set in the {doc}`../nydusfile`:

1. Files are classified by extension (binary files are skipped).
2. **Gitleaks** scans all text files in a temporary tree and replaces matched
   secrets with `{{SECRET_001}}`, `{{SECRET_002}}`, etc.
3. **Presidio** scans the (now secret-free) contents for PII entities and
   replaces them with `{{PII_001}}`, `{{PII_002}}`, etc.
4. A `SecretRecord` is created for each finding — kind `credential` (gitleaks)
   or `pii` (Presidio).
5. Raw artifacts in the `raw/` archive layer are also redacted.
6. All redaction events are recorded in `spawn_log.json`.

The spawner and any LLM refinement only ever see placeholder tokens, never real
values. See {doc}`../pipelines` for the full phase breakdown.

## Gitleaks (secrets)

Gitleaks must be installed on `$PATH` (or pointed to via `$NYDUS_GITLEAKS_PATH`)
when spawning with `REDACT true` and `SOURCE` directives. If gitleaks is missing,
`spawn()` raises `GitleaksNotFoundError` before any processing begins.

Install gitleaks: <https://github.com/gitleaks/gitleaks#installing>

Hatching and FROM-only spawns do not require gitleaks.

## Presidio (PII)

Presidio runs as a Python library using the `en_core_web_lg` spaCy model.
Custom recognizers cover SSNs, US passports, and driver's licenses. API key
detection is handled entirely by gitleaks — Presidio focuses on PII only.

## REDACT directive

The Nydusfile `REDACT` directive is a boolean toggle:

| Value | Secrets (gitleaks) | PII (Presidio) |
|-------|:------------------:|:--------------:|
| `true` (default) | Redacted | Redacted |
| `false` | Kept | Kept |

When `REDACT false` is set, a warning is logged. Real credentials and PII will
appear in the Egg — use only for testing or fully trusted environments.

## File classification

Files are classified by extension before scanning:

| Category | Extensions | Behaviour |
|----------|-----------|-----------|
| **Ignored** | `png`, `jpg`, `pdf`, `zip`, `exe`, etc. | Passed through unchanged |
| **Structured** | `json`, `yaml`, `yml` | Scanned as text (future: format-aware) |
| **Markdown** | `md`, `mdx` | Scanned as text (future: section-aware) |
| **Plain** | Everything else | Scanned as text |

## Re-personalization at hatch time

PII and secret placeholders can be resolved from a `.env` file at hatch time.
If no substitution is needed, placeholders remain in the output files. The
`.env` template can be generated with `nydus env`:

```bash
nydus env agent.egg -o agent.env
# Edit agent.env to fill in real values
nydus hatch agent.egg --target letta --secrets agent.env
```
