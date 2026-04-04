# CLI Reference

The `nydus` CLI is installed with `pip install pynydus`. All commands are thin
wrappers over the Python SDK. LLM and registry settings use environment
variables (see {doc}`/guides/configuration`).

## spawn

Create an Egg from source artifacts. Reads a `Nydusfile` from the current
directory.

```bash
nydus spawn [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-o`, `--output` | `PATH` | `./agent.egg` | Output Egg path |

---

## hatch

Deploy an Egg into a target runtime. Default mode is **rebuild** (generate
from structured modules). Use `--passthrough` to replay the archived `raw/`
snapshot verbatim.

```bash
nydus hatch <EGG_PATH> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `EGG_PATH` | `PATH` | (required) | Path to `.egg` file |
| `--target` | `TEXT` | (required) | Target: `openclaw`, `zeroclaw`, `letta` |
| `-o`, `--output` | `PATH` | `./agent/` | Output directory |
| `--secrets` | `PATH` | | `.env` substitution file |
| `--passthrough` | flag | `false` | Replay redacted `raw/` (requires target = source) |

---

## env

Generate a template `.env` from an Egg's secret requirements.

```bash
nydus env <EGG_PATH> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `EGG_PATH` | `PATH` | (required) | Path to `.egg` file |
| `-o`, `--output` | `PATH` | `./hatch.env` | Output `.env` path |

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

---

## validate

Check Egg integrity. Exits with code 1 if invalid.

```bash
nydus validate <EGG_PATH>
```

---

## diff

Compare two Eggs section-by-section (manifest, skills, memory, secrets).

```bash
nydus diff <EGG_A> <EGG_B>
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
| `--version` | `TEXT` | (required) | Version string |
| `--author` | `TEXT` | | Optional author override |

---

## pull

Download an Egg from the Nest registry.

```bash
nydus pull <NAME> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME` | `TEXT` | (required) | Registry name |
| `--version` | `TEXT` | (required) | Version to pull |
| `-o`, `--output` | `PATH` | `pulled.egg` | Output path |

---

## register

Register a new Nest account.

```bash
nydus register <USERNAME> [-p PASSWORD]
```

---

## login

Log in to Nest. Credentials stored at `~/.nydus/credentials.json`.

```bash
nydus login <USERNAME> [-p PASSWORD]
```

---

## logout

Remove stored Nest credentials.

```bash
nydus logout
```
