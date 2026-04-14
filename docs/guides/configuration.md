# Configuration

PyNydus loads **only environment variables**. There are no config files.


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

# Optional: non-default gitleaks binary (see getting-started/install)
# NYDUS_GITLEAKS_PATH=/path/to/gitleaks

# Optional: PEM text of Ed25519 private key (else ~/.nydus/keys/private.pem)
# NYDUS_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
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
| `NYDUS_PRIVATE_KEY` | No | File `~/.nydus/keys/private.pem` | When **set**: PEM **body** of the Ed25519 private key (not a path). When **unset**: `load_private_key()` reads `~/.nydus/keys/private.pem`. See {doc}`/guides/security`. |


LLM refinement requires both `NYDUS_LLM_TYPE` and `NYDUS_LLM_API_KEY`. If
both are unset, refinement is skipped. If only one is set, `load_config()`
raises `ValueError` whenever it runs (for example `nydus spawn`, `nydus hatch`,
registry commands, or constructing `Nydus()` in the SDK). Commands that never
call `load_config()` (such as `nydus inspect`, `env`, `extract`, `diff`,
`delete`) do not hit that error. See {doc}`/guides/llm-refinement`.
