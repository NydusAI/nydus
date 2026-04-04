# PyNydus

**Portable state transport for AI agents.**

PyNydus is the Python implementation of Nydus: a portable packaging layer for AI agents. Named after the Zerg Nydus Network from StarCraft (a transport tunnel that moves units instantly between any two locations), it transports agent state between frameworks without manual migration.

```bash
pip install pynydus
```

```
Source → Spawn → Egg → Hatch → Target
```

For a quick introduction, see {doc}`quickstart`. For the Egg data model and
archive layout, see {doc}`egg-format`. For the full spawn and hatch phase
breakdown, see {doc}`pipelines`.

## How it works

PyNydus defines a portable artifact called an **Egg** and bidirectional connectors
for encoding (**spawning**) and decoding (**hatching**) agent state:

- **Spawn**: read source agent artifacts, extract skills/memory/secrets, package into an Egg
- **Hatch**: decode an Egg into any supported target runtime, resolving secrets from a `.env` file (default **rebuild** from modules; optional **`--passthrough`** replays `raw/` when valid)
- **Share**: push/pull Eggs through the Nest registry

The Egg stores three modules with deterministic placeholder linking: every
redacted PII value or secret maps to a unique token with tracked occurrences.
Users re-personalize via a `.env` file at hatch time.

## Project structure

```text
pynydus/
├── api/              Egg data model, schemas, errors
├── agents/           Per-platform spawners + hatchers (openclaw, zeroclaw, letta)
├── engine/           Core pipelines: spawn, hatch, packager, validator, differ, merger, refinement
├── security/         Presidio, gitleaks, Ed25519 signing
├── cmd/              Typer CLI
├── client/           Python SDK (Nydus class)
├── common/           Shared enums, connector helpers, scan_paths
├── llm/              LLM tier models and Instructor client
├── config.py         Environment-based config loader
├── remote/           Nest registry client
└── eggs/base/        Base egg source definitions (Nydusfile + agent files per version)
tests/
├── unit/             Unit tests (mocked dependencies)
└── integration/      Integration tests (full pipeline, requires gitleaks)
```

## Contents

```{toctree}
:maxdepth: 2

quickstart
egg-format
pipelines
cli
nydusfile
configuration
architecture
troubleshooting
api/index
advanced/index
```
