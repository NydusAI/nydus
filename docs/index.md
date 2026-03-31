# pynydus

**Portable state transport for AI agents.**

pynydus is the Python SDK and CLI for [Nydus](https://github.com/NydusAI/nydus),
a portable packaging layer that moves AI agent state between frameworks without
manual migration.

```bash
pip install pynydus
```

Requires Python 3.10 or later.

## What pynydus does

pynydus reads agent files from any supported framework, strips credentials and
PII, packages the result into a portable `.egg` archive, and can unpack that
archive into any other supported framework. The full flow looks like this:

```
Source files  -->  nydus spawn  -->  .egg archive  -->  nydus hatch  -->  Target files
```

### Spawn

The `spawn` pipeline reads a Nydusfile, scans source files for credentials and
PII, replaces sensitive values with deterministic placeholders, classifies
content into skills, memory (with four semantic labels: persona, flow, context,
state), and secrets, then packages everything into a signed `.egg` ZIP archive.

### Hatch

The `hatch` pipeline takes an `.egg` archive and a target framework name,
maps labeled records into the file layout expected by the target, substitutes
secret placeholders from a user-provided `.env` file, and writes the output
directory. The target is chosen at hatch time, not at build time.

### Supported frameworks

| Framework | Spawn | Hatch | Notes |
|-----------|-------|-------|-------|
| OpenClaw  | Yes   | Yes   | Markdown files, skill.md, config.yaml |
| ZeroClaw  | Yes   | Yes   | Markdown, Python tools, identity.json, memory.db, config.toml |
| Letta     | Yes   | Yes   | JSON export, SQLite, .af AgentFile |

## Quick example

```bash
# Write a Nydusfile
echo 'SOURCE openclaw ./my-agent/' > Nydusfile
echo 'REDACT pii' >> Nydusfile

# Build an Egg
nydus spawn -o agent.egg

# Inspect what is inside
nydus inspect agent.egg --secrets --logs

# Generate a secrets template, fill it in, then hatch
nydus env agent.egg -o agent.env
nydus hatch agent.egg --target letta --secrets agent.env
```

Or the same thing from Python:

```python
from pynydus import Nydus

ny = Nydus()
egg = ny.spawn()
path = ny.pack(egg, output="agent.egg")

result = ny.hatch(egg, target="letta", secrets="agent.env")
print(result.output_dir, result.files_created)
```

## Links

- **GitHub**: <https://github.com/NydusAI/nydus>
- **PyPI**: <https://pypi.org/project/pynydus/>
- **Website**: <https://nydus.tech>

## Contents

```{toctree}
:maxdepth: 2

quickstart
cli
nydusfile
api/index
advanced/index
```
