# 01 REDACT: Travel Agent

A personal travel assistant with API keys in `config.json` and client
PII (name, email, phone) in workspace files. Nydus redacts both:
gitleaks catches credentials, Presidio catches PII. Placeholders are
substituted back at hatch time via a `.env` file.

## Prerequisites

- `pynydus` installed
- `gitleaks` v8+ on PATH
- spaCy model: `python -m spacy download en_core_web_lg`

## Run
```
./run.sh
```
## What to look for

- `nydus inspect --secrets` shows all detected placeholders
- `nydus env` generates a `.env` template from the egg
- Rebuild hatch produces a canonical OpenClaw workspace (uppercase
  filenames, `skills/` directory, `memory/` directory)
- Passthrough hatch preserves the original structure exactly

**Note:** Nydus only scans files matching the spawner's file patterns
(`*.md`, `*.json`, `*.yaml`, etc.). Files like `.env` are not read by
the pipeline. In this example, API keys are in `config.json` (a common
mistake in OpenClaw workspaces) which is where gitleaks detects them.

## Rebuild vs Passthrough

By default, `nydus hatch` uses **rebuild** mode: it reconstructs the
workspace from structured egg records into a canonical OpenClaw layout:

| Egg data | Rebuild output |
|---|---|
| persona memory | SOUL.md (+ IDENTITY.md if source had one) |
| flow memory | AGENTS.md |
| context memory | USER.md (+ TOOLS.md if source had one) |
| undated state memory | MEMORY.md |
| dated state memory | memory/YYYY-MM-DD.md |
| skills | skills/\<name\>.md (one per skill) |

**Passthrough** replays the redacted `raw/` snapshot from the egg,
keeping filenames, directory structure, and formatting as they were
at spawn time:
```
nydus hatch travel.egg --target openclaw -o ./hatched/ --passthrough
```
