# 02 ADD: Company Chatbot

A company support chatbot ("Zara") with a distinctive personality and
product knowledge. The base egg is spawned first, then extended with
`FROM` + `ADD` directives to layer on a new skill, new memory, and a
new database secret, without touching the original source files.

## Prerequisites

- `pynydus` installed (no external tools needed)

## Run
```
./run.sh
```

## What to look for

- `nydus inspect` on both eggs shows the base vs extended contents
- `nydus diff` shows exactly what ADD introduced: +1 skill, +2 memory,
  +1 secret
- The extend step uses FROM-only (no SOURCE), so it works purely from
  the `.egg` artifact — no access to the original workspace needed

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
