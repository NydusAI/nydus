# CLI Reference

The `nydus` command-line tool is installed with `pip install pynydus`. All
commands are thin wrappers over the Python SDK.

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
| `-c`, `--config` | `PATH` | `./config.json` | Path to config file (LLM keys) |

**Example:**

```text
# Nydusfile
SOURCE openclaw ./my-agent/
REDACT pii
PURPOSE "my personal assistant"
```

```bash
nydus spawn -o agent.egg
```

See {doc}`nydusfile` for the full Nydusfile DSL reference.

---

## hatch

Deploy an Egg into a target runtime. The target is chosen at hatch time.
Eggs are target-agnostic.

```bash
nydus hatch <EGG_PATH> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `EGG_PATH` | `PATH` | (required) | Path to `.egg` file |
| `--target` | `TEXT` | (required) | Target runtime: `openclaw`, `zeroclaw`, `letta` |
| `-o`, `--output` | `PATH` | `./agent/` | Output directory |
| `--secrets` | `PATH` | | Path to `.env` substitution file |
| `--reconstruct` | flag | `false` | Force regeneration from modules (skip pass-through) |
| `-c`, `--config` | `PATH` | `./config.json` | Path to config file (LLM keys) |

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
| `--author` | `TEXT` | from config | Author name |
| `--config` | `PATH` | `./config.json` | Path to config file |

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
| `--config` | `PATH` | `./config.json` | Path to config file |

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
| `--config` | `PATH` | `./config.json` | Path to config file |

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
| `--config` | `PATH` | `./config.json` | Path to config file |

Credentials are stored at `~/.nydus/credentials.json`.

---

## logout

Log out from the Nest registry.

```bash
nydus logout [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--config` | `PATH` | `./config.json` | Path to config file |

Removes the stored JWT token for the configured registry.
