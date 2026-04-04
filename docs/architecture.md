# Architecture

This page describes the high-level design of PyNydus: the data flow, module
responsibilities, and key design decisions.

## Data flow

```
┌─────────────┐     ┌───────────────────────────────────────────┐     ┌─────────────┐
│  Source     │     │              Nydus Engine                 │     │  Target     │
│  (OpenClaw, │     │                                           │     │  (OpenClaw, │
│   Letta,    │ ──> │ Spawn Pipeline ──> Egg ──> Hatch Pipeline │ ──> │   Letta,    │
│   ZeroClaw) │     │                                           │     │   ZeroClaw) │
└─────────────┘     └───────────────────────────────────────────┘     └─────────────┘
```

An agent's state flows through two pipelines with a portable **Egg** artifact
in the middle:

1. **Spawn** reads source files, redacts secrets/PII, extracts structured
   records, optionally refines them with an LLM, and packages everything into
   an Egg.
2. **Hatch** takes an Egg, renders it into a target platform's file format,
   optionally polishes with an LLM, injects real secrets, and writes to disk.

The Egg is the interchange format — a signed ZIP containing structured modules
(skills, memory, secrets) plus the redacted raw source snapshot.

## Spawn pipeline phases

| Phase | Module | What happens |
|-------|--------|-------------|
| 1. Parse Nydusfile | `engine/nydusfile.py` | Resolve `FROM`, `SOURCE`, `REDACT`, `EXCLUDE`, `LABEL`, `ADD/SET/REMOVE` |
| 2. Read source files | `engine/pipeline.py` | Read files matching spawner's `FILE_PATTERNS` from the source directory |
| 3. Secret scan | `security/gitleaks.py` | Replace credentials with `{{SECRET_NNN}}` placeholders |
| 4. PII redaction | `security/presidio.py` | Replace PII (emails, names, etc.) with `{{PII_NNN}}` placeholders |
| 5. Parse | `agents/*/spawner.py` | Platform-specific extraction into `ParseResult` (skills, memory, mcp configs) |
| 6. Build records | `engine/pipeline.py` | Normalize into `SkillRecord`, `MemoryRecord`, `SecretRecord` with IDs |
| 7. LLM refinement | `engine/refinement.py` | Deduplicate memory, normalize skills (operates on placeholder'd content only) |
| 8. Package | `engine/pipeline.py` | Build `Manifest` + `Egg`, apply directives (`EXCLUDE`, `LABEL`, `REMOVE`) |

## Hatch pipeline phases

| Phase | Module | What happens |
|-------|--------|-------------|
| 1. Version check | `engine/hatcher.py` | Reject eggs requiring a newer Nydus version |
| 2. Render files | `agents/*/hatcher.py` | Structured render from modules (rebuild) or raw snapshot replay (passthrough) |
| 3. LLM polish | `engine/refinement.py` | Adapt/polish for target platform conventions (on placeholder'd content) |
| 4. Secret injection | `engine/hatcher.py` | Substitute `{{SECRET_NNN}}` / `{{PII_NNN}}` with real values from `.env` |
| 5. Write to disk | `engine/hatcher.py` | Write output files to target directory |
| 6. Hatch log | `engine/hatcher.py` | Write `logs/hatch_log.json` with pipeline events |

## Module responsibilities

### `api/` — Data model

Pydantic schemas for `Egg`, `Manifest`, `SkillsModule`, `MemoryModule`,
`SecretsModule`, and all record types. Also defines `ParseResult` / `RenderResult`
(the spawner/hatcher I/O contracts) and the error hierarchy.

### `agents/` — Platform connectors

Each platform (OpenClaw, Letta, ZeroClaw) has:
- A **spawner** that implements `parse(files) -> ParseResult`
- A **hatcher** that implements `render(egg) -> RenderResult`

Connectors are pure functions over file dicts — no filesystem access during
parse/render. The pipeline handles file I/O.

### `engine/` — Core pipelines

- `pipeline.py` — spawn entry point, orchestrates all phases
- `hatcher.py` — hatch entry point, orchestrates all phases
- `nydusfile.py` — Nydusfile DSL parser
- `merger.py` — `FROM` base egg merge operations (`ADD`, `SET`, `REMOVE`)
- `refinement.py` — LLM refinement for spawn (dedup/normalize) and hatch (adapt/polish)
- `packager.py` — save/load `.egg` ZIP archives
- `validator.py` — structural egg validation
- `differ.py` — egg-to-egg diff

### `security/` — Redaction and signing

- `gitleaks.py` — wraps the gitleaks binary for credential scanning
- `presidio.py` — Microsoft Presidio for PII detection and redaction
- `signing.py` — Ed25519 key generation, signing, and verification

### `client/` — Python SDK

The `Nydus` class mirrors the CLI 1:1. `spawn()` returns an Egg with
`raw_artifacts` and `spawn_log` populated via `model_copy`. `save(sign=True)`
loads the private key automatically.

### `cmd/` — CLI

Typer-based CLI. Each command delegates to the SDK or engine directly.

## Key design decisions

### The Egg as interchange format

The Egg intentionally separates **structured modules** (skills, memory, secrets)
from the **raw snapshot** (`raw/` directory). This enables two hatch modes:
- **Rebuild** (default): render from structured modules via the target connector
- **Passthrough**: replay the raw snapshot verbatim (same-platform only)

### Placeholder linking

Every redacted value (secret or PII) gets a unique placeholder token
(`{{SECRET_001}}`, `{{PII_001}}`) tracked in `secrets.json` with:
- Occurrence locations (which files contain it)
- Whether it's required at hatch time
- The injection mode (substitution or env var)

This deterministic linking means the LLM refinement phase can operate freely
on placeholder'd content without ever seeing real secrets.

### LLM never sees real secrets

The security boundary is strict: redaction happens **before** parsing and LLM
refinement. Secret injection happens **after** LLM polish. The LLM only ever
operates on content containing `{{SECRET_NNN}}` / `{{PII_NNN}}` tokens.

### One SOURCE per Nydusfile

The current design enforces a single `SOURCE` directive per Nydusfile. This
keeps the pipeline simple — one source directory, one agent type, one set of
file patterns. Multi-source composition is achieved via `FROM` (base egg
merging) instead.

### Connectors are file-dict pure

Spawners and hatchers receive `dict[str, str]` (filename to content) and
return structured results. They never touch the filesystem. This makes them
trivially testable and ensures the pipeline controls all I/O, redaction
ordering, and placeholder management.
