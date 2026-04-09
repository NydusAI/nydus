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

How the scan works:

1. Scannable files (non-binary) are written to a temporary directory.
2. Gitleaks runs against the temp dir using its built-in rule set.
3. Findings are mapped back to the in-memory file dict.
4. Each matched span is replaced with a unique `{{SECRET_NNN}}` token.
5. Ignored (binary) files pass through unchanged.

Gitleaks must be installed when spawning with `REDACT true` and `SOURCE`
directives. See {doc}`/getting-started/install` for setup.


### Presidio (PII)

[Presidio](https://microsoft.github.io/presidio/) scans the
(already gitleaks-processed) files for PII and replaces each match with a
`{{PII_NNN}}` placeholder (kind `pii`).

**NLP model:** `en_core_web_lg` (spaCy). Loaded once and cached as a singleton.

**Confidence threshold:** 0.40. Detections below this score are discarded.

**Built-in entity types detected:**

| Entity type | Examples |
|-------------|---------|
| `PERSON` | Full names |
| `EMAIL_ADDRESS` | email@example.com |
| `PHONE_NUMBER` | +1-555-0123 |
| `CREDIT_CARD` | 4111-1111-1111-1111 |
| `IBAN_CODE` | GB82 WEST 1234 5698 7654 32 |
| `IP_ADDRESS` | 192.168.1.1 |
| `LOCATION` | "123 Main St, Springfield" |
| `MEDICAL_LICENSE` | Medical license numbers |

**Custom recognizers** (added by PyNydus):

| Entity type | Pattern | Context keywords |
|-------------|---------|-----------------|
| `US_SSN` | `\d{3}-\d{2}-\d{4}`, `\d{3} \d{2} \d{4}` | ssn, social security |
| `US_PASSPORT` | `[A-Z]\d{8}` | passport, travel document |
| `US_DRIVERS_LICENSE` | `[A-Z]\d{6,14}` | driver, license, dl |

**Suppressed entity types** (too noisy): `URL`, `DATE_TIME`, `NRP`.

**Overlap resolution:** When multiple detections overlap the same text span,
the highest-scoring, longest match wins. Others are discarded.

**Deduplication:** Identical PII values across files reuse the same placeholder.
"John Smith" in three files all become the same `{{PII_001}}`.


### File classification

Binary files are skipped during scanning. Classification is by extension:

**Ignored (binary):** `png`, `jpg`, `jpeg`, `gif`, `webp`, `ico`, `svg`,
`pdf`, `zip`, `egg`, `gz`, `tar`, `bz2`, `xz`, `7z`, `woff`, `woff2`,
`ttf`, `otf`, `eot`, `mp3`, `mp4`, `wav`, `ogg`, `webm`, `avi`, `bin`,
`exe`, `dll`, `so`, `dylib`, `pyc`, `pyo`, `class`.

**Scannable (everything else):** Markdown, JSON, YAML, plain text, Python, etc.


### REDACT directive

| Value | Secrets (gitleaks) | PII (Presidio) |
|-------|:------------------:|:--------------:|
| `true` (default) | Redacted | Redacted |
| `false` | Kept | Kept |


When `REDACT false` is set, a warning is logged. Use only for testing.

## Placeholder linking


Every redacted value gets a unique placeholder token. The Egg's `SecretsModule`
stores a `SecretRecord` for each:

| Field | Description |
|-------|-------------|
| `id` | Stable ID (`secret_001`, `pii_001`) |
| `placeholder` | The token (`{{SECRET_001}}`, `{{PII_001}}`) |
| `kind` | `credential` (gitleaks) or `pii` (Presidio) |
| `pii_type` | Entity type for PII records (e.g., `PERSON`, `EMAIL_ADDRESS`) |
| `name` | Human-readable name (e.g., `AWS_ACCESS_KEY_ID`, `PII_PERSON`) |
| `required_at_hatch` | If `true`, hatch fails without this secret in `.env` |
| `injection_mode` | How the value is substituted (`env` = `.env` file) |
| `description` | Optional description of what was redacted |
| `occurrences` | List of source files containing this placeholder |

`nydus env agent.egg` generates a template `.env` by reading all
`SecretRecord` entries and listing their names as keys to fill in.

## Injection boundary (secrets IN)


During hatch, secret injection is the **last transformation before writing to
disk**:

1. Connector renders files (placeholders intact)
2. LLM polishes files (placeholders intact)
3. **Secret injection**: `{{SECRET_NNN}}` / `{{PII_NNN}}` replaced with real
   values from `.env`
4. Files written to disk

The `.env` file maps `SecretRecord.name` -> real value. If a record has
`required_at_hatch=True` and its name is missing, hatch fails with an error
listing the missing secrets.

## Spawn log security


The spawn log captures detailed structured events from every pipeline step.
It is stored in the Egg and forwarded to the hatch LLM. No real secret values
or PII appear in the log:

- **Secret entries** log only the placeholder name and gitleaks rule ID.
  The actual secret value is never recorded.
- **PII entries** log only the entity type (e.g., `PERSON`) and the
  placeholder. The actual PII value is never recorded.
- **Text content** is logged as character lengths, never as raw text.
  For example, a memory record logs `text_length: 245`, not the text itself.

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
