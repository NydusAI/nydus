# Architecture

High-level design of PyNydus: data flow, pipeline phases, module
responsibilities, and key design decisions.

## Data flow

```
┌─────────────┐     ┌───────────────────────────────────────────┐     ┌─────────────┐
│  Source      │     │              Nydus Engine                 │     │  Target      │
│  (OpenClaw,  │     │                                           │     │  (OpenClaw,  │
│   Letta,     │ ──> │ Spawn Pipeline ──> Egg ──> Hatch Pipeline │ ──> │   Letta,     │
│   ZeroClaw)  │     │                                           │     │   ZeroClaw)  │
└─────────────┘     └───────────────────────────────────────────┘     └─────────────┘
```

An agent's state flows through two pipelines with a portable **Egg** in the
middle. The Egg is the interchange format, a signed ZIP containing structured
modules (skills, memory, secrets) plus a redacted raw source snapshot.

## Spawn pipeline

Entry point: `pynydus.engine.pipeline.spawn()`. Returns `(egg, raw_artifacts, logs)`.

| Phase | Module | What happens |
|-------|--------|-------------|
| 1. Parse Nydusfile | `engine/nydusfile.py` | Resolve `FROM`, `SOURCE`, `REDACT`, `EXCLUDE`, `LABEL`, merge ops |
| 2. Read source files | `engine/pipeline.py` | Read files matching spawner's `FILE_PATTERNS`, apply `REMOVE file` drops |
| 3. Secret scan | `security/gitleaks.py` | Replace credentials with `{{SECRET_NNN}}` placeholders |
| 4. PII redaction | `security/presidio.py` | Replace PII with `{{PII_NNN}}` placeholders |
| 5. Parse | `agents/*/spawner.py` | Platform-specific extraction into `ParseResult` |
| 6. Build records | `engine/pipeline.py` | Normalize into `SkillRecord`, `MemoryRecord`, `SecretRecord` with stable IDs |
| 7. LLM refinement | `engine/refinement.py` | Deduplicate memory, normalize skills (placeholder'd content only) |
| 8. Package | `engine/pipeline.py` | Build `Manifest` + `Egg`, apply `EXCLUDE`, `LABEL` |

Phases 3–4 form the **secrets OUT boundary**. After them, no real credentials
or PII exist in the pipeline. The spawner (phase 5) and LLM (phase 7) only
see placeholder tokens. See {doc}`/guides/security` for details.

When no Nydusfile exists, PyNydus probes each spawner's `detect()`. If multiple
types match, spawn fails with an ambiguous layout error.

## Hatch pipeline

Entry point: `pynydus.engine.hatcher.hatch()`.

| Phase | Module | What happens |
|-------|--------|-------------|
| 1. Version check | `engine/hatcher.py` | Reject eggs requiring a newer Nydus version |
| 2. Render files | `agents/*/hatcher.py` | Rebuild from modules (default) or passthrough replay of `raw/` |
| 3. LLM polish | `engine/refinement.py` | Adapt/polish for target conventions (placeholder'd content only) |
| 4. Secret injection | `engine/hatcher.py` | Substitute `{{SECRET_NNN}}` / `{{PII_NNN}}` from `.env` |
| 5. Write to disk | `engine/hatcher.py` | Write output files |
| 6. Hatch log | `engine/hatcher.py` | Write `logs/hatch_log.json` |

Phase 4 is the **secrets IN boundary**, the last transformation before disk.

**Hatch modes:**
- **Rebuild** (default): render from structured modules via target connector.
- **Passthrough** (`--passthrough`): replay redacted `raw/` verbatim. Requires
  target = source type and non-empty `raw/`.

## Module responsibilities

### `api/`: Data model

Pydantic schemas for `Egg`, `Manifest`, modules, and record types. Also defines
`ParseResult` / `RenderResult` (spawner/hatcher I/O contracts) and errors.

### `agents/`: Platform connectors

Each platform has a **spawner** (`parse(files) -> ParseResult`) and a
**hatcher** (`render(egg) -> RenderResult`). Connectors are pure functions over
file dicts with no filesystem access. See {doc}`/reference/connectors`.

### `engine/`: Core pipelines

- `pipeline.py`: spawn orchestration
- `hatcher.py`: hatch orchestration
- `nydusfile.py`: Nydusfile DSL parser
- `merger.py`: `FROM` base egg merge operations
- `refinement.py`: LLM refinement (spawn + hatch)
- `packager.py`: `.egg` ZIP I/O
- `validator.py`: structural egg validation
- `differ.py`: egg-to-egg diff

### `security/`: Redaction and signing

- `gitleaks.py`: credential scanning
- `presidio.py`: PII detection and redaction
- `signing.py`: Ed25519 key generation, signing, verification

### `client/`: Python SDK

The `Nydus` class mirrors the CLI 1:1.

### `cmd/`: CLI

Typer-based CLI. Each command delegates to the SDK or engine.

## Key design decisions

**Egg as interchange format.** Structured modules (skills, memory, secrets) are
separated from the raw snapshot (`raw/`). This enables rebuild (cross-platform)
and passthrough (same-platform) hatch modes.

**Placeholder linking.** Every redacted value gets a unique token tracked with
occurrence locations. The LLM can operate freely on placeholder'd content
without seeing real secrets.

**LLM never sees real secrets.** Redaction before parsing, injection after LLM
polish. Strict ordering enforced by pipeline.

**One SOURCE per Nydusfile.** Keeps the pipeline simple: one source, one type,
one set of file patterns. Multi-source via `FROM` merging.

**Connectors are file-dict pure.** Spawners/hatchers take `dict[str, str]` and
return structured results. No filesystem access = trivially testable.
