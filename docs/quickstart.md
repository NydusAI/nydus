# Quickstart

This guide walks through the full pynydus workflow: install the package, write
a Nydusfile, spawn an Egg, inspect it, and hatch it into a different framework.

## Install

```bash
pip install pynydus
```

Requires Python 3.10 or later. This installs both the `nydus` CLI and the
Python SDK.

Verify the installation:

```bash
nydus --help
```

## Prepare a source agent

pynydus works with agent directories on disk. For this guide, assume you have
an OpenClaw agent with the following files:

```text
my-agent/
  SOUL.md           # "I am Maya, a customer support agent..."
  AGENTS.md         # "Always greet users warmly. Escalate billing to a human."
  USER.md           # "The user prefers email communication."
  knowledge.md      # "Company returns policy: 30-day window..."
  skill.md          # "# Order Lookup\nGiven an order ID..."
  config.yaml       # api_key: sk-abc123...
```

## Write a Nydusfile

Create a file named `Nydusfile` (no extension) in your working directory. The
Nydusfile declares which sources to read and what redaction policy to apply:

```text
SOURCE openclaw ./my-agent/
REDACT pii
```

`SOURCE` takes a framework name (`openclaw`, `zeroclaw`, or `letta`) and a path.
`REDACT pii` enables both credential scanning and PII redaction. See the
{doc}`nydusfile` reference for the full list of directives.

## Spawn an Egg

Build a portable `.egg` archive from the sources declared in your Nydusfile:

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

During spawning, the pipeline:

1. Scans config files for credentials and replaces them with `{{SECRET_NNN}}` placeholders
2. Optionally redacts PII (names, emails, phone numbers) into `{{PII_NNN}}` placeholders
3. Classifies each file into a semantic category: persona, flow, context, or state
4. Extracts skills from `skill.md` into the Agent Skills format
5. Packages everything into a ZIP archive with a manifest, memory records, secret records, and skill bundles

The important safety property: all redaction happens **before** any content
parsing. The spawner never sees raw credentials or PII.

## Inspect the Egg

See what is inside the archive:

```bash
nydus inspect agent.egg
```

Add `--secrets` to list all placeholder mappings, and `--logs` for the pipeline
activity log:

```bash
nydus inspect agent.egg --secrets --logs
```

You can also validate the Egg's structural integrity:

```bash
nydus validate agent.egg
```

## Generate a secrets template

Before hatching, you need to supply real values for the placeholders. Generate
a starter `.env` file:

```bash
nydus env agent.egg -o agent.env
```

This produces a file like:

```text
SECRET_001=       # api_key (credential)
```

Fill in the real values for your target environment.

## Hatch into another framework

Deploy the Egg into a different framework. The target is chosen at hatch time,
not at build time:

**CLI:**

```bash
nydus hatch agent.egg --target letta --secrets agent.env -o ./letta-agent/
```

**Python SDK:**

```python
result = ny.hatch(egg, target="letta", secrets="agent.env")
print(result.output_dir)
print(result.files_created)
```

The hatcher maps labeled memory records into the target's file layout, converts
skills into the target's tool format, and substitutes secret placeholders from
the `.env` file. The output directory is a fully formed agent ready to run in
the target framework.

## Share via Nest

Publish a versioned Egg to the Nest registry so others can pull it:

```bash
nydus login myuser
nydus push agent.egg --name myuser/my-agent --version 0.1.0
```

Pull it from another machine:

```bash
nydus pull myuser/my-agent --version 0.1.0 -o agent.egg
```

## Multi-source Nydusfile

Nydusfiles support multiple `SOURCE` directives. Combine inputs from different
frameworks into a single Egg:

```text
SOURCE openclaw ./my-agent/
SOURCE letta ./letta-agent/
REDACT pii
PURPOSE "multilingual data engineering assistant"
```

Records from all sources are pooled, deduplicated, and merged into one Egg.

## Compare two Eggs

Track how an agent changes over time by diffing two versions:

```bash
nydus diff v1.egg v2.egg
```

This prints added, removed, and modified records across all modules (manifest,
skills, memory, secrets).

## Next steps

- {doc}`cli` for the full CLI command reference
- {doc}`nydusfile` for all Nydusfile directives (FROM, INCLUDE, EXCLUDE, LABEL, and more)
- {doc}`api/index` for Python SDK and data model reference
- {doc}`advanced/signing` for Egg signing and verification
- {doc}`advanced/nest` for registry operations
- {doc}`advanced/connectors` for adding support for a new framework
