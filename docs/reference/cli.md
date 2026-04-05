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

| Flag | Default | Description |
|------|---------|-------------|
| `-o`, `--output` | `./agent.egg` | Output Egg path |

---

## hatch


Deploy an Egg into a target runtime. Default mode is **rebuild** (generate
from structured modules). Use `--passthrough` to replay the archived `raw/`
snapshot verbatim.


```bash
nydus hatch <EGG_PATH> [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `EGG_PATH` | (required) | Path to `.egg` file |
| `--target` | (required) | Target: `openclaw`, `zeroclaw`, `letta` |
| `-o`, `--output` | `./agent/` | Output directory |
| `--secrets` | (none) | `.env` substitution file |
| `--passthrough` | `false` | Replay redacted `raw/` (requires target = source) |

---

## env


Generate a template `.env` from an Egg's secret requirements.


```bash
nydus env <EGG_PATH> [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `EGG_PATH` | (required) | Path to `.egg` file |
| `-o`, `--output` | `./hatch.env` | Output `.env` path |

---

## inspect


Print Egg summary.


```bash
nydus inspect <EGG_PATH> [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `EGG_PATH` | (required) | Path to `.egg` file |
| `--secrets` | `false` | List all placeholders and occurrences |
| `--logs` | `false` | Show pipeline log summary |

---

## validate


Check Egg integrity. Exits with code 1 if invalid.


```bash
nydus validate <EGG_PATH>
```

| Flag | Default | Description |
|------|---------|-------------|
| `EGG_PATH` | (required) | Path to `.egg` file |

---

## diff


Compare two Eggs section-by-section (manifest, skills, memory, secrets).


```bash
nydus diff <EGG_A> <EGG_B>
```

| Flag | Default | Description |
|------|---------|-------------|
| `EGG_A` | (required) | First `.egg` file |
| `EGG_B` | (required) | Second `.egg` file |

---

## delete


Delete an Egg file.


```bash
nydus delete <EGG_PATH>
```

| Flag | Default | Description |
|------|---------|-------------|
| `EGG_PATH` | (required) | Path to `.egg` file |

---

## keygen


Generate an Ed25519 keypair for Egg signing.


```bash
nydus keygen [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--dir` | `~/.nydus/keys/` | Directory to write keys to |

---

## push


Publish an Egg to the Nest registry.


```bash
nydus push <EGG_PATH> [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `EGG_PATH` | (required) | Path to `.egg` file |
| `--name` | (required) | Registry name (e.g. `user/my-agent`) |
| `--version` | (required) | Version string |
| `--author` | (none) | Author override |

---

## pull


Download an Egg from the Nest registry.


```bash
nydus pull <NAME> [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `NAME` | (required) | Registry name |
| `--version` | (required) | Version to pull |
| `-o`, `--output` | `pulled.egg` | Output path |

---

## register


Register a new Nest account.


```bash
nydus register <USERNAME> [-p PASSWORD]
```

| Flag | Default | Description |
|------|---------|-------------|
| `USERNAME` | (required) | Account username |
| `-p` | (prompted) | Password |

---

## login


Log in to Nest. Credentials stored at `~/.nydus/credentials.json`.


```bash
nydus login <USERNAME> [-p PASSWORD]
```

| Flag | Default | Description |
|------|---------|-------------|
| `USERNAME` | (required) | Account username |
| `-p` | (prompted) | Password |

---

## logout


Remove stored Nest credentials.


```bash
nydus logout
```
