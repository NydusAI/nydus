# CLI Reference

The `nydus` command-line tool is installed with the PyNydus package (`pip install pynydus`). All
commands are thin wrappers over the Python SDK.

LLM refinement and Nest registry access use **environment variables** (`NYDUS_LLM_TYPE`,
`NYDUS_LLM_API_KEY`, `NYDUS_REGISTRY_URL`, …). See {doc}`configuration`.

## spawn

Create an Egg from source artifacts. Reads a `Nydusfile` from the current
directory and fails if none is found. All source paths, redaction settings,
and other spawn configuration are declared in the Nydusfile.

```bash
nydus spawn [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-o`, `--output` | `PATH` | `./agent.egg` | Output Egg path |

**Example:**

```text
# Nydusfile
SOURCE openclaw ./my-agent/
REDACT true
```

```bash
nydus spawn -o agent.egg
```

See {doc}`nydusfile` for the full Nydusfile DSL reference.

---

## hatch

Deploy an Egg into a target runtime. The target is chosen at hatch time.
Eggs are target-agnostic.

**Default behavior is rebuild:** output files are generated from the structured egg
(skills, memory, secrets) via the target hatcher. Use **`--passthrough`** only when
you want to replay the archived redacted `raw/` tree verbatim; that requires the
hatch `--target` to match the egg's source type and non-empty `raw/` in the archive.

```bash
nydus hatch <EGG_PATH> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `EGG_PATH` | `PATH` | (required) | Path to `.egg` file |
| `--target` | `TEXT` | (required) | Target runtime: `openclaw`, `zeroclaw`, `letta` |
| `-o`, `--output` | `PATH` | `./agent/` | Output directory |
| `--secrets` | `PATH` | | Path to `.env` substitution file |
| `--passthrough` | flag | `false` | Replay redacted `raw/` snapshot (requires target match egg source) |

**Example:**

```bash
nydus hatch agent.egg --target letta --secrets agent.env -o ./letta-agent/
```

---

## env

Generate a template `.env` file from an Egg's secret requirements. Edit the
generated file to fill in real values before passing it to `nydus hatch`.

```bash
nydus env <EGG_PATH> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `EGG_PATH` | `PATH` | (required) | Path to `.egg` file |
| `-o`, `--output` | `PATH` | `./hatch.env` | Output `.env` path |

**Example:**

```bash
nydus env agent.egg -o agent.env
# Edit agent.env to fill in real values
nydus hatch agent.egg --target letta --secrets agent.env
```

---

## inspect

Print Egg summary.

```bash
nydus inspect <EGG_PATH> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `EGG_PATH` | `PATH` | (required) | Path to `.egg` file |
| `--secrets` | flag | `false` | List all placeholders and occurrences |
| `--logs` | flag | `false` | Show pipeline log summary |

**Example:**

```bash
nydus inspect agent.egg --secrets --logs
```

---

## validate

Check Egg integrity.

```bash
nydus validate <EGG_PATH>
```

Runs structural validation: module consistency, placeholder references,
skill_ref integrity, signature status. Exits with code 1 if invalid.

**Example:**

```bash
nydus validate agent.egg
```

---

## diff

Compare two Eggs.

```bash
nydus diff <EGG_A> <EGG_B>
```

Prints a section-by-section diff (manifest, skills, memory, secrets) showing
added, removed, and modified records.

**Example:**

```bash
nydus diff v1.egg v2.egg
```

---

## delete

Delete an Egg file.

```bash
nydus delete <EGG_PATH>
```

---

## keygen

Generate an Ed25519 keypair for egg signing.

```bash
nydus keygen [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--dir` | `PATH` | `~/.nydus/keys/` | Directory to write keys to |

Generates `private.pem` (permissions 600) and `public.pem`. When a private key
exists, `nydus spawn` automatically signs the Egg.

**Example:**

```bash
nydus keygen
```

---

## push

Publish an Egg to the Nest registry.

```bash
nydus push <EGG_PATH> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `EGG_PATH` | `PATH` | (required) | Path to `.egg` file |
| `--name` | `TEXT` | (required) | Registry name (e.g. `user/my-agent`) |
| `--version` | `TEXT` | (required) | Version string (e.g. `0.1.0`) |
| `--author` | `TEXT` | | Optional author override (defaults to `NYDUS_REGISTRY_AUTHOR` if set) |

**Example:**

```bash
nydus push agent.egg --name myuser/my-agent --version 0.1.0
```

---

## pull

Download an Egg from the Nest registry.

```bash
nydus pull <NAME> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME` | `TEXT` | (required) | Registry name (e.g. `user/my-agent`) |
| `--version` | `TEXT` | (required) | Version to pull |
| `-o`, `--output` | `PATH` | `pulled.egg` | Output path |

**Example:**

```bash
nydus pull myuser/my-agent --version 0.1.0 -o agent.egg
```

---

## register

Register a new account on the Nest registry.

```bash
nydus register <USERNAME> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `USERNAME` | `TEXT` | (required) | Username |
| `-p`, `--password` | `TEXT` | (prompted) | Password (hidden input) |

---

## login

Log in to the Nest registry and store credentials.

```bash
nydus login <USERNAME> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `USERNAME` | `TEXT` | (required) | Username |
| `-p`, `--password` | `TEXT` | (prompted) | Password (hidden input) |

Credentials are stored at `~/.nydus/credentials.json`.

---

## logout

Log out from the Nest registry.

```bash
nydus logout
```

Removes the stored JWT token for the registry at `NYDUS_REGISTRY_URL`.
