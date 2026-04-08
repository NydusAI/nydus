# 03 LLM Refinement: Cloud Verbose → Local Compressed

A DevOps advisor agent ("Atlas") with a verbose persona, detailed
operating instructions, six weeks of accumulated daily memory, and
extensive domain reference notes. Nydus LLM refinement compresses
memory and tightens skills during spawn, preserving meaning while
reducing token count.

## Prerequisites

- `pynydus` installed
- For compressed spawn: `export NYDUS_LLM_TYPE=openai/gpt-4o` and
  `export NYDUS_LLM_API_KEY=sk-...`

## Run
```
./run.sh
```
Without LLM env vars, the script spawns `verbose.egg` and exits.
With them set, it also spawns `compressed.egg` and runs a diff.

## What to look for

- `nydus diff` shows memory record count decreasing (deduplication of
  overlapping SOUL.md/AGENTS.md instructions + weekly memory overlap)
- Skill content is shorter (tightened prose, same capabilities)
- Word count comparison shows 30–50% reduction
- Meaning is preserved (no dropped capabilities or knowledge)

**Note:** Compression is non-deterministic. The LLM produces different
output on each run. Results are reproducible in character but not
identical across runs.

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

**Passthrough** replays the redacted `raw/` snapshot byte-for-byte:
```
nydus hatch agent.egg --target openclaw -o ./hatched/ --passthrough
```
