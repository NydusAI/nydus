# CLI Reference

The `nydus` CLI is installed with `pip install pynydus`. Commands mirror the
Python SDK behavior but call the same engine and registry modules directly (they
are not implemented as thin wrappers around the `Nydus` class). LLM and
registry settings use environment variables (see {doc}`/guides/configuration`).

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
| `--no-validate` | `false` | Skip per-standard schema validation |

---

## extract


Extract standard artifacts from an Egg. Subcommands: `mcp`, `skills`, `a2a`,
`apm`, `agents`, `specs`, `all`.


```bash
nydus extract <SUBCOMMAND> --from <EGG_PATH> [-o <OUTPUT_DIR>]
```

| Subcommand | Default output | Description |
|------------|----------------|-------------|
| `mcp` | `.` | Extract `mcp.json` |
| `skills` | `.` | Extract `skills/<slug>/SKILL.md` files |
| `a2a` | `.` | Extract `agent-card.json` |
| `apm` | `.` | Extract `apm.yml` (passthrough) |
| `agents` | `.` | Extract per-egg `AGENTS.md` |
| `specs` | `./specs` | Extract embedded spec snapshots |
| `all` | `./extracted` | Extract all artifacts at once |

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
nydus register <USERNAME>
```

| Flag | Default | Description |
|------|---------|-------------|
| `USERNAME` | (required) | Account username |
| `--password`, `-p` | (prompted if omitted) | Password (hidden prompt) |

---

## login


Log in to Nest. Credentials stored at `~/.nydus/credentials.json`.


```bash
nydus login <USERNAME>
```

| Flag | Default | Description |
|------|---------|-------------|
| `USERNAME` | (required) | Account username |
| `--password`, `-p` | (prompted if omitted) | Password (hidden prompt) |

---

## logout


Remove stored Nest credentials.


```bash
nydus logout
```
