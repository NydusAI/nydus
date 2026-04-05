# Installation

## PyNydus

Requires Python 3.10+.

```bash
pip install pynydus
```

### Verify the installation

```bash
nydus --help
```

You should see the list of available commands (`spawn`, `hatch`, `inspect`, etc.).

### Supported platforms

| Platform | Spawn | Hatch |
|----------|:-----:|:-----:|
| OpenClaw | Yes | Yes |
| ZeroClaw | Yes | Yes |
| Letta | Yes | Yes |

### Core concepts

| Term | Meaning |
|------|---------|
| **Egg** | The portable artifact. In memory it is an `Egg` object (manifest + skills + memory + secrets). On disk it is a `.egg` ZIP archive. |
| **Spawn** | Read source files, redact secrets/PII, parse structure, and package into an Egg. |
| **Hatch** | Read an Egg, render target files, resolve secrets, and write to disk. |
| **Nydusfile** | A small DSL file declaring what to spawn: source type, redaction settings, and merge operations. |

## Gitleaks (external)

Spawning with `REDACT true` (the default) requires
[gitleaks](https://github.com/gitleaks/gitleaks) for secret scanning.

```bash
# macOS
brew install gitleaks

# Linux
curl -sSL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_8.21.2_linux_x64.tar.gz \
  | tar xz -C /usr/local/bin gitleaks

# From source (requires Go 1.22+)
go install github.com/gitleaks/gitleaks/v8@latest
```

### Verify gitleaks

```bash
gitleaks version
```

Version 8.18+ is recommended.

### Custom location

If the binary is not on `$PATH`, set `NYDUS_GITLEAKS_PATH`:

```bash
export NYDUS_GITLEAKS_PATH=/path/to/gitleaks
```

### When is gitleaks needed?

| Operation | Gitleaks required? |
|-----------|:------------------:|
| `nydus spawn` with `REDACT true` (default) | Yes |
| `nydus spawn` with `REDACT false` | No |
| `nydus spawn` with `FROM` only (no `SOURCE`) | No |
| `nydus hatch` | No |
| `nydus inspect`, `validate`, `diff` | No |

## Optional: LLM refinement

To enable LLM-backed refinement during spawn and hatch, set two environment
variables:

```bash
export NYDUS_LLM_TYPE=anthropic/claude-haiku-4-5-20251001
export NYDUS_LLM_API_KEY=sk-your-key
```

If both are unset, refinement is skipped (no error). See
{doc}`/guides/configuration` for all environment variables.

## Next steps

Continue to the {doc}`quickstart` to spawn and hatch your first Egg.
