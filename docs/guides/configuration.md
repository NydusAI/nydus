# Configuration

PyNydus loads **only environment variables**. There are no config files.

## Quick setup

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Example `.env`:

```bash
# LLM refinement (both required together, omit both to skip refinement)
NYDUS_LLM_TYPE=openai/gpt-4o
NYDUS_LLM_API_KEY=sk-your-key-here

# Nest registry (required for push/pull and FROM resolution)
# NYDUS_REGISTRY_URL=http://localhost:8000
# NYDUS_REGISTRY_AUTHOR=your-name
```

For tests, `.env` is loaded automatically by `pytest-dotenv`.

## All variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `NYDUS_LLM_TYPE` | With `NYDUS_LLM_API_KEY` | (none) | LLM provider/model for refinement (e.g. `anthropic/claude-haiku-4-5-20251001`) |
| `NYDUS_LLM_API_KEY` | With `NYDUS_LLM_TYPE` | (none) | API key for the LLM provider |
| `NYDUS_REGISTRY_URL` | For push/pull | (none) | Nest registry base URL (e.g. `http://localhost:8000`) |
| `NYDUS_REGISTRY_AUTHOR` | No | (none) | Default author for pushes |
| `NYDUS_GITLEAKS_PATH` | No | `gitleaks` on PATH | Gitleaks binary location |
| `NYDUS_PRIVATE_KEY` | No | `~/.nydus/nydus_ed25519` | Ed25519 private key for signing |

## How variables are resolved

PyNydus reads variables from the process environment at import time via
`pynydus.config.load_config()`. The SDK (`Nydus()`) and the CLI both call
this automatically.

- **LLM refinement** requires both `NYDUS_LLM_TYPE` and `NYDUS_LLM_API_KEY`.
  If both are unset, refinement is skipped (no error). If only one is set,
  `load_config()` raises `ValueError`. See {doc}`/guides/llm-refinement`.
- **Nest registry** operations (`push`, `pull`, `FROM` resolution) require
  `NYDUS_REGISTRY_URL`. Without it, those commands fail with a clear error.
- **Gitleaks** is found on `$PATH` by default. Override with
  `NYDUS_GITLEAKS_PATH` if it is installed elsewhere.
- **Signing** uses `~/.nydus/nydus_ed25519` by default. Override with
  `NYDUS_PRIVATE_KEY` to point to a different key file.
