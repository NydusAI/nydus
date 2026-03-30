# Quickstart

Get up and running with pynydus in six steps.

## 1. Install

```bash
pip install pynydus
```

Requires Python 3.10+.

## 2. Write a Nydusfile

Create a `Nydusfile` in your project directory declaring what to spawn:

```text
SOURCE openclaw ./my-agent/
REDACT pii
```

## 3. Spawn an Egg

**CLI:**

```bash
nydus spawn -o agent.egg
```

**Python SDK:**

```python
from pynydus import Nydus

ny = Nydus()
egg = ny.spawn()  # reads ./Nydusfile
ny.pack(egg, output="agent.egg")
```

The spawner reads the sources declared in your Nydusfile, extracts skills,
memory, and secrets, redacts PII using Presidio, and packages everything into
a portable `.egg` archive.

## 4. Inspect the Egg

See what's inside:

```bash
nydus inspect agent.egg --secrets --logs
```

This prints the manifest metadata, module counts (skills, memory, secrets),
signature status, and optionally a table of all secret placeholders and a
summary of pipeline log activity.

## 5. Hatch into another runtime

Deploy the Egg into a different framework:

**CLI:**

```bash
nydus hatch agent.egg --target letta --secrets agent.env
```

**Python SDK:**

```python
result = ny.hatch(egg, target="letta", secrets="agent.env")
print(result.files_created)
```

The hatcher resolves secret placeholders from the `.env` file, transforms
skills and memory into the target's native format, and writes the output
directory.

## 6. Share via Nest

Push your Egg to the Nest registry:

```bash
nydus login myuser
nydus push agent.egg --name myuser/my-agent --version 0.1.0
```

Pull it from another machine:

```bash
nydus pull myuser/my-agent --version 0.1.0 -o agent.egg
```

## Multi-source Nydusfile

Nydusfiles support multiple SOURCE directives. Combine different input types
into a single Egg:

```text
SOURCE openclaw ./my-agent/
SOURCE letta ./letta-agent/
REDACT pii
PURPOSE "multilingual data engineering assistant"
```

```bash
nydus spawn -o agent.egg
```

See {doc}`nydusfile` for the full DSL reference.

## Next steps

- {doc}`cli`: CLI reference
- {doc}`api/index`: Python SDK reference
- {doc}`nydusfile`: full Nydusfile DSL reference
- {doc}`advanced/connectors`: add support for a new framework
