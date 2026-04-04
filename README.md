<p align="center">
  <img src="https://raw.githubusercontent.com/NydusAI/nydus/main/assets/logo.png" alt="Nydus" width="420">
</p>

<p align="center">
  <strong>Portable state transport for AI agents</strong><br>
  Transport agent state between any two frameworks without manual migration
</p>

<p align="center">
  <a href="https://pypi.org/project/pynydus/"><img src="https://img.shields.io/pypi/v/pynydus?color=blue" alt="PyPI"></a>
  <a href="https://pypi.org/project/pynydus/"><img src="https://img.shields.io/pypi/pyversions/pynydus" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  <a href="https://pynydus.readthedocs.io/en/latest/?badge=latest"><img src="https://readthedocs.org/projects/pynydus/badge/?version=latest" alt="Docs"></a>
  <a href="#status"><img src="https://img.shields.io/badge/status-early%20development-orange" alt="Status"></a>
</p>

<p align="center">
  <a href="https://pynydus.readthedocs.io/en/latest/">Docs</a> •
  <a href="#install">Install</a> •
  <a href="#how-it-works">How it works</a> •
  <a href="#cli">CLI</a> •
  <a href="#python-sdk">Python SDK</a> •
  <a href="#development">Development</a>
</p>

---

## How it works

- **Spawn**: read source agent artifacts, redact PII, and package everything into a portable **Egg** (`.egg` archive)
- **Hatch**: decode an Egg into any supported target runtime, with optional LLM refinement and secret injection

```
Source artifacts → Spawn → Egg (.egg) → Hatch → Target-native files
```

### The Egg format

An `.egg` file is a signed ZIP archive containing:

```
manifest.json          # metadata, source type, versions
memory.json            # labeled memory records
secrets.json           # PII placeholders + secret requirements
skills/<slug>/SKILL.md # portable skill definitions (agentskills.io)
mcp/<server>.json      # MCP server configs
raw/...                # redacted source files (for passthrough mode hatch)
```

## Install

```bash
pip install pynydus
```

### Prerequisites

**Gitleaks** is required for spawning when `REDACT true` (the default) and
`SOURCE` directives are present. Gitleaks scans source files for secrets
(API keys, tokens, passwords). Install it before running `nydus spawn`:

```bash
# macOS
brew install gitleaks

# Linux (download from GitHub releases)
curl -sSL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_8.21.2_linux_x64.tar.gz \
  | tar xz -C /usr/local/bin gitleaks

# Or build from source (requires Go 1.22+)
go install github.com/gitleaks/gitleaks/v8@latest
```

If gitleaks is installed in a non-standard location, set `NYDUS_GITLEAKS_PATH`:

```bash
export NYDUS_GITLEAKS_PATH=/opt/bin/gitleaks
```

Hatching (and `FROM`-only spawns without `SOURCE`) does **not** require gitleaks.

## CLI

```bash
# Create a Nydusfile in your project directory
cat > Nydusfile << 'EOF'
SOURCE openclaw ./my-agent/
REDACT true
EOF

# Spawn an egg
nydus spawn -o agent.egg

# Inspect and validate
nydus inspect agent.egg
nydus inspect agent.egg --secrets --logs
nydus validate agent.egg

# Generate a template .env from the egg's secret requirements
nydus env agent.egg -o agent.env

# Hatch into a target runtime
nydus hatch agent.egg --target letta --secrets agent.env

# Compare two eggs
nydus diff v1.egg v2.egg

# Signing
nydus keygen
nydus spawn -o signed.egg  # auto-signs if key exists
```

## Python SDK

```python
from pathlib import Path

from pynydus import Nydus
from pynydus.common.enums import AgentType

ny = Nydus()

# Spawn from a Nydusfile in the current directory
egg = ny.spawn()
ny.save(egg, Path("agent.egg"))

# Load and hatch into a target runtime
egg = ny.load(Path("agent.egg"))
result = ny.hatch(egg, target=AgentType.LETTA, secrets="agent.env")
print(result.output_dir, result.files_created)
```

## Project structure

```
pynydus/
  api/           # Egg data model, schemas, errors
  agents/        # Per-platform spawners + hatchers (openclaw, zeroclaw, letta)
  engine/        # Core pipelines: spawn, hatch, save/load egg, validate, diff, merge, refine
  security/      # Presidio, gitleaks, Ed25519 signing
  cmd/           # Typer CLI
  client/        # Python SDK (Nydus class)
  common/        # Shared enums, connector helpers, scan_paths
  llm/           # LLM tier models and Instructor client
  config.py      # Environment-based config loader
  remote/        # Nest registry client
  eggs/base/     # Base egg source definitions (Nydusfile + agent files per version)
tests/
  unit/          # Unit tests (mocked dependencies)
  integration/   # Integration tests (full pipeline, requires gitleaks)
```

## Configuration

Set environment variables for LLM refinement and the Nest registry. Copy
`[.env.example](.env.example)` to `.env` and fill in your values. See the
[Configuration](docs/guides/configuration.md) doc for all available settings
(`NYDUS_LLM_TYPE`, `NYDUS_LLM_API_KEY`, `NYDUS_REGISTRY_URL`, etc.).

## Development

```bash
uv sync --group dev
```

### Tests

Tests are split into `tests/unit/` and `tests/integration/` with dedicated Make targets:

```bash
make test-unit          # fast, no external deps
make test-integration   # full pipeline, requires gitleaks
make test               # both (excludes live LLM)
make test-live-llm      # requires .env with NYDUS_LLM_TYPE + NYDUS_LLM_API_KEY
```

Integration tests require **gitleaks** on `PATH` (see [Prerequisites](#prerequisites)).

For live LLM tests, copy `.env.example` to `.env` and fill in your API key. The
`.env` file is loaded automatically by `pytest-dotenv`.

### Code style

```bash
make fmt          # Ruff formatter + auto-fix lint
make check        # CI-style check (no writes)
```

### Documentation

Full documentation is hosted at
[pynydus.readthedocs.io](https://pynydus.readthedocs.io/en/latest/).
API reference is generated with [Sphinx](https://www.sphinx-doc.org/) and
[sphinx-autodoc2](https://sphinx-autodoc2.readthedocs.io/) (`make docs`).

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development guide.

## Status

Early development. APIs and on-disk formats may change between releases.

## License

MIT