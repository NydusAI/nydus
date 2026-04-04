# Security model

This page describes PyNydus's security architecture: how secrets and PII are
handled throughout the spawn and hatch pipelines, and the trust boundaries
between components.

## Overview

PyNydus enforces a strict principle: **no real secret or PII value should
exist in the Egg or be visible to the LLM**. The pipeline achieves this
through ordered redaction, deterministic placeholder linking, and a
late-binding injection boundary.

```
Source files (contain real secrets + PII)
    │
    ▼
┌──────────────────────┐
│  Phase 3: Gitleaks   │  Credentials → {{SECRET_NNN}}
│  Phase 4: Presidio   │  PII → {{PII_NNN}}
└──────────────────────┘
    │
    ▼
Redacted files (only placeholders, no real values)
    │
    ├──> Spawner.parse()     (sees placeholders only)
    ├──> LLM refinement      (sees placeholders only)
    ├──> Egg archive          (stores placeholders only)
    ├──> LLM hatch polish     (sees placeholders only)
    │
    ▼
┌──────────────────────┐
│  Phase 4: Secret IN  │  {{SECRET_NNN}} → real values from .env
└──────────────────────┘
    │
    ▼
Output files (real values restored)
```

## Redaction boundary (secrets OUT)

During spawn, redaction happens **before** any parsing or LLM calls:

1. **Gitleaks** scans source files for credentials (API keys, tokens,
   passwords) and replaces each match with a `{{SECRET_NNN}}` placeholder.
   Each placeholder is tracked as a `SecretRecord` with the rule ID, original
   location, and whether it's required at hatch time.

2. **Presidio** scans the (already gitleaks-processed) files for PII — email
   addresses, phone numbers, person names, etc. — and replaces each with a
   `{{PII_NNN}}` placeholder. These are also tracked as `SecretRecord` entries
   with `kind=PII`.

The spawner connector, LLM refinement, and everything downstream only ever see
placeholder tokens. The raw source snapshot stored in `raw/` also contains only
placeholders.

## Placeholder linking

Each `SecretRecord` in `secrets.json` contains:

| Field | Purpose |
|-------|---------|
| `id` | Unique identifier (e.g. `secret_001`, `pii_002`) |
| `placeholder` | The token string (e.g. `{{SECRET_001}}`) |
| `kind` | `credential` or `pii` |
| `name` | Human-readable name (e.g. `OPENAI_API_KEY`, `PII_EMAIL`) |
| `required_at_hatch` | Whether the secret must be provided for hatch |
| `injection_mode` | How to inject: `substitution` (in-file replace) or `env` |
| `occurrences` | Which files contain this placeholder |

This deterministic linking allows `nydus env` to generate a template `.env`
file listing exactly which secrets the egg needs.

## Injection boundary (secrets IN)

During hatch, secret injection is the **last transformation before writing to
disk** (Phase 4 of 6):

1. Connector renders files (with placeholders still present)
2. LLM polishes files (with placeholders still present)
3. **Secret injection**: `{{SECRET_NNN}}` / `{{PII_NNN}}` replaced with real
   values from the `.env` file
4. Files written to disk

This ordering ensures the LLM never sees real values.

## Egg signing (Ed25519)

Eggs can be signed with Ed25519 keys to ensure integrity and authenticity:

- **Signing** happens during `save()` — the manifest, modules, and raw
  artifacts are hashed and signed. The signature is stored in
  `signature.json` inside the archive.
- **Verification** happens during `load()` — if a `signature.json` is present,
  it's verified against the public key. Tampering with any file in the archive
  invalidates the signature.

Key management:

| Path | Purpose |
|------|---------|
| `~/.nydus/nydus_ed25519` | Private key (auto-used by `nydus spawn`) |
| `~/.nydus/nydus_ed25519.pub` | Public key (shared for verification) |
| `NYDUS_PRIVATE_KEY` env var | Override private key path |

Generate keys with `nydus keygen`.

## LLM trust boundary

The LLM is an untrusted component — it can modify content but never sees
real secrets. The pipeline enforces this by:

1. Running redaction **before** the LLM sees any content
2. Running injection **after** the LLM has finished
3. Validating LLM output: unknown file paths are dropped, unknown record IDs
   are skipped with a warning

If the LLM fails or returns invalid output, the pipeline falls back to the
original unrefined content. No data is lost.

## File classification

The pipeline classifies source files before scanning. Binary files, images,
and other non-text content are excluded from gitleaks and Presidio scanning
(and from the spawner). See `pynydus/common/scan_paths.py` for the
classification logic.

## Recommendations

- Always use `REDACT true` (the default) when spawning from real agent projects
- Generate and use signing keys for eggs shared between teams
- Use `nydus env` to create `.env` templates rather than guessing secret names
- Review the spawn log (`nydus inspect --logs`) to verify redaction coverage
- Keep gitleaks updated — newer versions detect more credential patterns
