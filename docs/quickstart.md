# Quickstart

Get up and running with PyNydus in six steps.

## Core concepts

| Term | Meaning |
|------|---------|
| **Egg** | The portable artifact. In memory it is an `Egg` object (manifest + skills + memory + secrets). On disk it is a `.egg` ZIP archive. |
| **Spawn** | Read source files, redact secrets/PII, parse structure, and package into an Egg. |
| **Hatch** | Read an Egg, render target files, resolve secrets, and write to disk. |
| **Nydusfile** | A small DSL file declaring what to spawn: at most one `SOURCE`, `REDACT`, **`EXCLUDE`** (memory buckets), **`REMOVE file`** (source file globs) or merger **`REMOVE`** (with `FROM`), `LABEL`, and merge ops. |
| **Spawner** | Platform-specific parser under `pynydus/agents/<name>/spawner.py`. Receives pre-redacted file contents and produces a `ParseResult`. |
| **Hatcher** | Platform-specific renderer under `pynydus/agents/<name>/hatcher.py`. Produces a `RenderResult` (file dict with placeholders). |
| **Bucket** | One of `skill`, `memory`, `secret`. Top-level module categories in an Egg. |

## Supported platforms

| Platform | Spawn | Hatch |
|----------|-------|-------|
| OpenClaw | Yes | Yes |
| ZeroClaw | Yes | Yes |
| Letta | Yes | Yes |

## 1. Install

```bash
pip install pynydus
```

Requires Python 3.10+.

### External dependency: gitleaks

Spawning with `REDACT true` (the default) and `SOURCE` directives requires
[gitleaks](https://github.com/gitleaks/gitleaks) for secret scanning:

```bash
# macOS
brew install gitleaks

# Linux
curl -sSL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_8.21.2_linux_x64.tar.gz \
  | tar xz -C /usr/local/bin gitleaks
```

If the binary is not on `$PATH`, set `NYDUS_GITLEAKS_PATH` to its location.
Hatching does not require gitleaks.

**Developers:** Running the full test suite (`make test`) also requires
gitleaks on `PATH` (or `NYDUS_GITLEAKS_PATH`) — the same prerequisite as spawn
with redaction. Run `make test-unit` for tests that don't need gitleaks. See
[CONTRIBUTING.md](https://github.com/NydusAI/nydus/blob/main/nydus/CONTRIBUTING.md)
for the full development guide.

## 2. Write a Nydusfile

Create a `Nydusfile` in your project directory declaring what to spawn:

```text
SOURCE openclaw ./my-agent/
REDACT true
```

## 3. Spawn an Egg

**CLI:**

```bash
nydus spawn -o agent.egg
```

**Python SDK:**

```python
from pathlib import Path
from pynydus import Nydus

ny = Nydus()
egg = ny.spawn()  # reads ./Nydusfile
ny.save(egg, Path("agent.egg"))
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
from pynydus.common.enums import AgentType

result = ny.hatch(egg, target=AgentType.LETTA, secrets="agent.env")
print(result.files_created)
```

The hatcher resolves secret placeholders from the `.env` file, transforms
skills and memory into the target's native format, and writes the output
directory.

### How secrets flow

Credentials and PII are replaced with placeholders **before** any parsing or
rendering. Real values are only substituted when hatching with a `.env` file:

```text
SPAWN:   source files ──[secrets OUT]──→ raw (placeholders) ──[parse]──→ records ──→ egg
                         ↑                                      ↑
                    real values replaced                   spawner only sees
                    with {{SECRET_NNN}}                   redacted content

HATCH:   egg ──→ records ──[render]──→ raw (placeholders) ──[secrets IN]──→ target files
                             ↑                                  ↑
                        hatcher only produces              {{SECRET_NNN}} replaced
                        placeholder'd content              with real values from .env
```

### Hatch modes

By default, **rebuild** regenerates target files from the structured egg (skills,
memory, secrets). To replay the redacted `raw/` snapshot instead, use **`--passthrough`**
on the CLI. That requires the hatch `--target` to match the egg's source type and a
non-empty `raw/` layer in the archive; otherwise the command fails with a clear error.

In Python, pass `mode="passthrough"` to {py:meth}`~pynydus.client.client.Nydus.hatch` (with
non-empty `raw_artifacts`).

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

## One source per Nydusfile

Each Nydusfile may declare **at most one** `SOURCE` line. To work with several
agent trees, merge them under one directory or maintain separate Nydusfiles.

```text
SOURCE openclaw ./my-agent/
REDACT true
```

```bash
nydus spawn -o agent.egg
```

See {doc}`nydusfile` for the full DSL reference.

**`EXCLUDE` vs file skipping:** `EXCLUDE` drops structured **memory** by bucket after parse.
To omit **files** from read/redact/parse under `SOURCE`, use **`REMOVE file <glob>`** (see
{doc}`nydusfile`). Merger-style **`REMOVE skill …`** applies to a **`FROM`** base egg.

## Next steps

- {doc}`cli`: CLI reference
- {doc}`api/index`: Python SDK reference
- {doc}`nydusfile`: full Nydusfile DSL reference
- {doc}`advanced/connectors`: add support for a new framework
