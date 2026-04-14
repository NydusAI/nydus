# Architecture

High-level design of PyNydus: data flow, pipeline steps, module
responsibilities, and key design decisions.

## Data flow


```
┌──────────────┐     ┌───────────────────────────────────────────┐     ┌──────────────┐
│  Source      │     │              Nydus Engine                 │     │  Target      │
│  (OpenClaw,  │     │                                           │     │  (OpenClaw,  │
│   Letta,     │ ──> │ Spawn Pipeline ──> Egg ──> Hatch Pipeline │ ──> │   Letta,     │
│   ZeroClaw)  │     │                                           │     │   ZeroClaw)  │
└──────────────┘     └───────────────────────────────────────────┘     └──────────────┘
```


An agent's state flows through two pipelines with a portable **Egg** in the
middle. The Egg is the interchange format: a signed ZIP containing structured
modules (Skills, Memory, Secrets) plus a redacted raw source snapshot.

Memory records carry one of four labels: Memory[**persona**],
Memory[**flow**], Memory[**context**], or Memory[**state**].

## Spawn pipeline


The spawn pipeline has 10 steps: resolve base egg, read source files, redact
secrets/PII, parse sources, build records, merge with base egg, LLM refinement,
post-processing, package egg, and generate standard artifacts.

Step 3 is the **secrets OUT boundary**. After it, no real credentials or PII
exist anywhere in the pipeline.

Every step appends structured entries to `spawn_log`, which is stored in the
egg and forwarded to the hatch LLM as full JSON context.

See {doc}`/design/spawn-pipeline` for the step-by-step deep dive.

## Hatch pipeline


The hatch pipeline has 6 steps: version check, build file dict, LLM polish,
secrets IN, write to disk, and hatch log.

Step 4 is the **secrets IN boundary**, the last transformation before disk.

Two modes: **rebuild** (default, generates from structured modules) and
**passthrough** (replays redacted `raw/` verbatim, requires target = source).

See {doc}`/design/hatch-pipeline` for the step-by-step deep dive.

## Module responsibilities


### `api/`: Data model

Pydantic schemas for `Egg`, `Manifest`, modules, and record types. Also defines
`ParseResult` / `RenderResult` (spawner/hatcher I/O contracts) and errors.


### `agents/`: Platform connectors

Each platform has a **spawner** (`parse(files) -> ParseResult`) and a
**hatcher** (`render(egg, output_dir) -> RenderResult`). Both must subclass the
`Spawner` / `Hatcher` ABCs from `pynydus.api.protocols`. See {doc}`/design/connectors`.

Each platform directory also contains an `AGENT_SPEC.md` that defines the
platform's workspace conventions. These specs are loaded at hatch time and
injected into the LLM prompt so the model can adapt output to match target
platform idioms. See {doc}`/guides/llm-refinement`.


### `engine/`: Core pipelines

- `pipeline.py`: spawn orchestration (Steps 1-10)
- `hatcher.py`: hatch orchestration (Steps 1-6)
- `nydusfile.py`: Nydusfile DSL parser
- `merger.py`: `FROM` base egg merge operations
- `refinement.py`: LLM refinement (spawn Step 7 + hatch Step 3)
- `packager.py`: `.egg` ZIP I/O
- `validator.py`: structural egg validation
- `standards/`: per-standard modules (MCP, skills, A2A, APM, AGENTS.md)
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


**Connectors are structured I/O.** Spawners take `dict[str, str]` and return
`ParseResult`. Hatchers take an `Egg` plus output directory and return
`RenderResult`. Both subclass ABCs defined in `pynydus.api.protocols`.
