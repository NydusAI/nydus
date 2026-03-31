# CLI Reference

The `nydus` command-line tool is installed with `pip install pynydus`. Every
command is a thin wrapper over the Python SDK, so anything you do in the CLI
can also be done programmatically.

## Core workflow

These commands cover the primary spawn-inspect-hatch loop.

### spawn

Create an Egg from source artifacts declared in a Nydusfile. The Nydusfile must
exist in the current directory (or be reachable via config).

```bash
nydus spawn [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `-o`, `--output` | `PATH` | `./agent.egg` | Output Egg path |
| `-c`, `--config` | `PATH` | `./config.json` | Path to config file (LLM keys, registry) |

Example:

```bash
nydus spawn -o agent.egg
```

The pipeline reads each SOURCE in the Nydusfile, runs credential scanning and
optional PII redaction, classifies content into skills/memory/secrets, and
writes the `.egg` archive. If a signing key exists at `~/.nydus/keys/private.pem`,
the Egg is signed automatically.

### hatch

Deploy an Egg into a target framework. The target is chosen at hatch time. Eggs
are framework-agnostic.

```bash
nydus hatch <EGG_PATH> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `EGG_PATH` | `PATH` | (required) | Path to `.egg` file |
| `--target` | `TEXT` | (required) | Target framework: `openclaw`, `zeroclaw`, `letta` |
| `-o`, `--output` | `PATH` | `./agent/` | Output directory |
| `--secrets` | `PATH` | | Path to `.env` file for placeholder substitution |
| `--reconstruct` | flag | `false` | Force regeneration from modules (skip pass-through) |
| `-c`, `--config` | `PATH` | `./config.json` | Path to config file |

Example:

```bash
nydus hatch agent.egg --target letta --secrets agent.env -o ./letta-agent/
```

The hatcher maps labeled records into the target's file layout, substitutes
secret placeholders from the `.env` file, and writes files to the output
directory. If the Egg is signed, the signature is verified before hatching.

### inspect

Print a summary of an Egg's contents: manifest metadata, module counts (skills,
memory, secrets), and signature status.

```bash
nydus inspect <EGG_PATH> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `EGG_PATH` | `PATH` | (required) | Path to `.egg` file |
| `--secrets` | flag | `false` | List all placeholders with their kind and occurrence count |
| `--logs` | flag | `false` | Show the pipeline log summary from spawning |

Example:

```bash
nydus inspect agent.egg --secrets --logs
```

### validate

Check an Egg's structural integrity. Runs module consistency checks, verifies
placeholder references, checks skill_ref integrity, and reports signature
status. Exits with code 1 if the Egg is invalid.

```bash
nydus validate <EGG_PATH>
```

Example:

```bash
nydus validate agent.egg
```

### env

Generate a template `.env` file from an Egg's secret requirements. Each
placeholder gets a line with its name, kind, and an empty value for you to fill
in. Use this before hatching.

```bash
nydus env <EGG_PATH> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `EGG_PATH` | `PATH` | (required) | Path to `.egg` file |
| `-o`, `--output` | `PATH` | `./hatch.env` | Output `.env` path |

Example:

```bash
nydus env agent.egg -o agent.env
# Edit agent.env to fill in real values
nydus hatch agent.egg --target letta --secrets agent.env
```

### diff

Compare two Eggs side by side. Prints added, removed, and modified records
across all modules (manifest, skills, memory, secrets). Useful for tracking
how an agent changes across versions.

```bash
nydus diff <EGG_A> <EGG_B>
```

Example:

```bash
nydus diff v1.egg v2.egg
```

---

## Signing

Commands for Ed25519 key management. See {doc}`advanced/signing` for full
details on how signing and verification work.

### keygen

Generate an Ed25519 keypair for Egg signing.

```bash
nydus keygen [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--dir` | `PATH` | `~/.nydus/keys/` | Directory to write keys to |

Creates `private.pem` (permissions 600) and `public.pem`. Once a private key
exists, `nydus spawn` signs Eggs automatically.

Example:

```bash
nydus keygen
nydus spawn -o signed.egg  # auto-signed
```

---

## Registry (Nest)

Commands for publishing and pulling Eggs from the Nest registry. See
{doc}`advanced/nest` for authentication setup and configuration.

### push

Publish a local Egg to the Nest registry.

```bash
nydus push <EGG_PATH> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `EGG_PATH` | `PATH` | (required) | Path to `.egg` file |
| `--name` | `TEXT` | (required) | Registry name (`user/agent-name`) |
| `--version` | `TEXT` | (required) | Semantic version string |
| `--author` | `TEXT` | from config | Author name |
| `--config` | `PATH` | `./config.json` | Path to config file |

Example:

```bash
nydus push agent.egg --name myuser/my-agent --version 0.1.0
```

### pull

Download an Egg from the Nest registry. The downloaded file is verified against
the server's SHA-256 checksum.

```bash
nydus pull <NAME> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `NAME` | `TEXT` | (required) | Registry name (`user/agent-name`) |
| `--version` | `TEXT` | (required) | Version to pull |
| `-o`, `--output` | `PATH` | `pulled.egg` | Output path |
| `--config` | `PATH` | `./config.json` | Path to config file |

Example:

```bash
nydus pull myuser/my-agent --version 0.1.0 -o agent.egg
```

### register

Register a new account on the Nest registry.

```bash
nydus register <USERNAME> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `USERNAME` | `TEXT` | (required) | Username |
| `-p`, `--password` | `TEXT` | (prompted) | Password (hidden input) |
| `--config` | `PATH` | `./config.json` | Path to config file |

### login

Log in to the Nest registry and store credentials locally.

```bash
nydus login <USERNAME> [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `USERNAME` | `TEXT` | (required) | Username |
| `-p`, `--password` | `TEXT` | (prompted) | Password (hidden input) |
| `--config` | `PATH` | `./config.json` | Path to config file |

Credentials (JWT tokens) are stored at `~/.nydus/credentials.json`.

### logout

Log out from the Nest registry and remove stored credentials.

```bash
nydus logout [OPTIONS]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--config` | `PATH` | `./config.json` | Path to config file |

---

## Utility

### delete

Delete an Egg file from disk.

```bash
nydus delete <EGG_PATH>
```
