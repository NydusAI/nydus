# Configuration

PyNydus loads **only environment variables** — there is no `config.json` or other project config file for global settings.

Copy `.env.example` in the repository root to `.env` and fill in your values:

```bash
cp .env.example .env
```

For tests, `.env` is loaded automatically by `pytest-dotenv`.

## LLM tier (refinement)

Set **both** of the following to enable LLM-backed refinement during spawn and hatch:

| Variable | Meaning |
|----------|---------|
| `NYDUS_LLM_TYPE` | `provider/model` (e.g. `anthropic/claude-haiku-4-5-20251001`) |
| `NYDUS_LLM_API_KEY` | API key for that provider/model |

If **both** are unset, `llm` is omitted (refinement is skipped). If **only one** is set, `load_config()` raises `ValueError`.

See {doc}`advanced/llm-refinement` for behavior details.

## Nest registry

| Variable | Meaning |
|----------|---------|
| `NYDUS_REGISTRY_URL` | Base URL of the Nest server (e.g. `http://localhost:8000`) — required for `push`, `pull`, and resolving `FROM nydus/...` refs |
| `NYDUS_REGISTRY_AUTHOR` | Optional default author for pushes |

## Security

| Variable | Meaning |
|----------|---------|
| `NYDUS_GITLEAKS_PATH` | Path to the gitleaks binary (default: looks on `$PATH`) |
| `NYDUS_PRIVATE_KEY` | Path to an Ed25519 private key for egg signing (default: `~/.nydus/nydus_ed25519`) |

## All variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `NYDUS_LLM_TYPE` | With `NYDUS_LLM_API_KEY` | — | LLM provider/model for refinement |
| `NYDUS_LLM_API_KEY` | With `NYDUS_LLM_TYPE` | — | API key for the LLM provider |
| `NYDUS_REGISTRY_URL` | For push/pull | — | Nest registry base URL |
| `NYDUS_REGISTRY_AUTHOR` | No | — | Default author for pushes |
| `NYDUS_GITLEAKS_PATH` | No | `gitleaks` on PATH | Gitleaks binary location |
| `NYDUS_PRIVATE_KEY` | No | `~/.nydus/nydus_ed25519` | Ed25519 private key for signing |
