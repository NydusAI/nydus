<p align="center">
  <img src="assets/logo.png" alt="Nydus" width="420">
</p>

<p align="center">
  <strong>Portable state transport for AI agents</strong><br>
  Transport agent state between any two frameworks without manual migration
</p>

<p align="center">
  <a href="https://pypi.org/project/pynydus/"><img src="https://img.shields.io/pypi/v/pynydus?color=blue" alt="PyPI"></a>
  <a href="https://pypi.org/project/pynydus/"><img src="https://img.shields.io/pypi/pyversions/pynydus" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  <a href="#status"><img src="https://img.shields.io/badge/status-early%20development-orange" alt="Status"></a>
</p>

<p align="center">
  <a href="#install">Install</a> •
  <a href="#how-it-works">How it works</a> •
  <a href="#cli">CLI</a> •
  <a href="#python-sdk">Python SDK</a> •
  <a href="#supported-platforms">Platforms</a>
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
raw/...                # redacted source files (for pass-through hatch)
```

## Install

```bash
pip install pynydus
```

## CLI

```bash
# Create a Nydusfile in your project directory
cat > Nydusfile << 'EOF'
SOURCE openclaw ./my-agent/
REDACT pii
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
from pynydus.client import Nydus

ny = Nydus()

# Spawn from a Nydusfile in the current directory
egg_path = ny.spawn()

# Hatch into a target runtime with secret injection
result = ny.hatch(egg_path, target="letta", secrets="agent.env")
print(result.output_dir, result.files_created)
```

## Project structure

```
pynydus/
  api/           # Egg data model, schemas, errors
  agents/        # Per-platform spawners + hatchers
    openclaw/
    zeroclaw/
    letta/
  engine/        # Core pipelines: spawn, hatch, pack, validate, diff, refine
  cmd/           # Typer CLI
  client/        # Python SDK
  pkg/           # Utilities: presidio, LLM, signing, config
  remote/        # Nest registry client
```

## License

MIT
