# Configuration

PyNydus loads **only environment variables**. There are no config files.

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

For tests, `.env` is loaded automatically by `pytest-dotenv`.

## All variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `NYDUS_LLM_TYPE` | With `NYDUS_LLM_API_KEY` | — | LLM provider/model for refinement (e.g. `anthropic/claude-haiku-4-5-20251001`) |
| `NYDUS_LLM_API_KEY` | With `NYDUS_LLM_TYPE` | — | API key for the LLM provider |
| `NYDUS_REGISTRY_URL` | For push/pull | — | Nest registry base URL (e.g. `http://localhost:8000`) |
| `NYDUS_REGISTRY_AUTHOR` | No | — | Default author for pushes |
| `NYDUS_GITLEAKS_PATH` | No | `gitleaks` on PATH | Gitleaks binary location |
| `NYDUS_PRIVATE_KEY` | No | `~/.nydus/nydus_ed25519` | Ed25519 private key for signing |

**LLM refinement** requires both `NYDUS_LLM_TYPE` and `NYDUS_LLM_API_KEY`.
If both are unset, refinement is skipped. If only one is set, `load_config()`
raises `ValueError`. See {doc}`llm-refinement`.
