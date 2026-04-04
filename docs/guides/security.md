# Security

PyNydus enforces a strict principle: **no real secret or PII value should
exist in the Egg or be visible to the LLM**. This page covers the full
security model: redaction, placeholder linking, signing, and trust boundaries.

## Redaction boundary (secrets OUT)

During spawn, redaction happens **before** any parsing or LLM calls:

```
Source files (contain real secrets + PII)
    │
    ▼
┌──────────────────────┐
│  Gitleaks            │  Credentials → {{SECRET_NNN}}
│  Presidio            │  PII → {{PII_NNN}}
└──────────────────────┘
    │
    ▼
Redacted files (only placeholders)
    │
    ├──> Spawner.parse()     (sees placeholders only)
    ├──> LLM refinement      (sees placeholders only)
    ├──> Egg archive          (stores placeholders only)
    ├──> LLM hatch polish     (sees placeholders only)
    │
    ▼
┌──────────────────────┐
│  Secret injection    │  {{SECRET_NNN}} → real values from .env
└──────────────────────┘
    │
    ▼
Output files (real values restored)
```

### Gitleaks (credentials)

[Gitleaks](https://github.com/gitleaks/gitleaks) scans source files for API
keys, tokens, and passwords, replacing each match with a `{{SECRET_NNN}}`
placeholder. Each finding becomes a `SecretRecord` with kind `credential`.

Gitleaks must be installed when spawning with `REDACT true` and `SOURCE`
directives. See {doc}`/getting-started/install` for setup.

### Presidio (PII)

[Presidio](https://microsoft.github.io/presidio/) scans the
(already gitleaks-processed) files for PII (emails, phone numbers, person
names, SSNs, etc.) and replaces each with a `{{PII_NNN}}` placeholder (kind
`pii`). Uses the `en_core_web_lg` spaCy model with custom recognizers.

### REDACT directive

| Value | Secrets (gitleaks) | PII (Presidio) |
|-------|:------------------:|:--------------:|
| `true` (default) | Redacted | Redacted |
| `false` | Kept | Kept |

When `REDACT false` is set, a warning is logged. Use only for testing.

### File classification

| Category | Extensions | Behaviour |
|----------|-----------|-----------|
| **Ignored** | `png`, `jpg`, `pdf`, `zip`, `exe`, … | Passed through unchanged |
| **Structured** | `json`, `yaml`, `yml` | Scanned as text |
| **Markdown** | `md`, `mdx` | Scanned as text |
| **Plain** | Everything else | Scanned as text |

## Placeholder linking

Each `SecretRecord` in `secrets.json` tracks:

| Field | Purpose |
|-------|---------|
| `placeholder` | Token string (`{{SECRET_001}}`) |
| `kind` | `credential` or `pii` |
| `name` | Human-readable name (e.g. `OPENAI_API_KEY`) |
| `required_at_hatch` | Must be provided at hatch time |
| `injection_mode` | `substitution` (in-file replace) or `env` |
| `occurrences` | Which files contain this placeholder |

This deterministic linking lets `nydus env` generate a template `.env` file
listing exactly which secrets an egg needs.

## Injection boundary (secrets IN)

During hatch, secret injection is the **last transformation before writing to
disk**:

1. Connector renders files (placeholders intact)
2. LLM polishes files (placeholders intact)
3. **Secret injection**: `{{SECRET_NNN}}` / `{{PII_NNN}}` replaced with real
   values from `.env`
4. Files written to disk

## Egg signing (Ed25519)

Eggs can be signed with Ed25519 keys for integrity and authenticity.

### Key generation

```bash
nydus keygen
```

Creates `private.pem` (permissions 600) and `public.pem` in `~/.nydus/keys/`.
Custom directory: `nydus keygen --dir ./my-keys/`.

### How signing works

When a private key exists at `~/.nydus/keys/private.pem` (or via
`NYDUS_PRIVATE_KEY`), `nydus spawn` automatically signs the egg:

1. Serialize manifest, skills, memory, and secrets into ordered byte arrays
2. Compute SHA-256 over the canonical content
3. Sign with Ed25519 private key
4. Store in `manifest.signature` and `signature.json` inside the archive

### Verification

Happens automatically during `nydus hatch`:

- **Valid**: hatching proceeds
- **Invalid**: hatching is rejected
- **Unsigned**: hatching proceeds silently

Check status anytime: `nydus inspect agent.egg`.

### SDK signing

```python
ny.save(egg, Path("agent.egg"), sign=True)
```

## LLM trust boundary

The LLM is an untrusted component. It can modify content but never sees
real secrets:

1. Redaction runs **before** the LLM sees content
2. Injection runs **after** the LLM finishes
3. Unknown file paths or record IDs in LLM output are dropped with a warning
4. If the LLM fails, the pipeline falls back to unrefined content

## Recommendations

- Always use `REDACT true` (the default) for real agent projects
- Generate signing keys for eggs shared between teams (`nydus keygen`)
- Use `nydus env` to create `.env` templates rather than guessing secret names
- Review spawn logs (`nydus inspect --logs`) to verify redaction coverage
- Keep gitleaks updated for broader credential pattern detection
