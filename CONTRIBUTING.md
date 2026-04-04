# Contributing to PyNydus

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (package manager)
- [gitleaks](https://github.com/gitleaks/gitleaks#installing) (required for integration tests and spawning with `REDACT true`)

## Setup

```bash
git clone https://github.com/NydusAI/nydus.git
cd nydus/nydus
uv sync --group dev
```

Verify everything works:

```bash
make test-unit
```

## Project layout

```
pynydus/
  api/           Egg data model, schemas, errors
  agents/        Per-platform spawners + hatchers (openclaw, zeroclaw, letta)
  engine/        Core pipelines: spawn, hatch, packager, validator, differ, merger, refinement
  cmd/           Typer CLI (nydus spawn, hatch, inspect, ...)
  client/        Python SDK (Nydus class)
  common/        Shared enums, connector helpers, scan_paths
  security/      Presidio PII redaction, gitleaks secret scanning, Ed25519 signing
  llm/           LLM tier models and Instructor client
  config.py      Environment-based config loader
  remote/        Nest registry client
  eggs/base/     Base egg source definitions (Nydusfile + agent files per version)
tests/
  conftest.py    Shared fixtures (make_egg, openclaw_project, etc.)
  helpers.py     Shared test helpers
  unit/          Unit tests (mocked dependencies, fast)
  integration/   Integration tests (real pipeline, requires gitleaks)
```

## Running tests

Tests are organized into three tiers with dedicated Make targets:

| Command | What it runs | Requirements |
|---------|-------------|--------------|
| `make test` | Unit + integration, excludes live LLM | gitleaks on PATH |
| `make test-unit` | Unit tests only | None |
| `make test-integration` | Integration tests only | gitleaks on PATH |
| `make test-live-llm` | Live LLM API tests | `.env` with `NYDUS_LLM_TYPE` + `NYDUS_LLM_API_KEY` |
| `make cov` | Unit + integration with coverage | gitleaks on PATH |

### Test markers

Tests use pytest markers defined in `pyproject.toml`:

- **`integration`** — full pipeline tests (spawn -> save -> load -> hatch). These require `gitleaks` installed and exercise real redaction.
- **`live_llm`** — tests that make real LLM API calls. Requires a `.env` file (loaded automatically via `pytest-dotenv`):

```bash
cp .env.example .env
# Edit .env with your real API key
make test-live-llm
```

### Writing tests

- **Unit tests** go in `tests/unit/`. Mock external dependencies. Assert on output content, not mock call counts.
- **Integration tests** go in `tests/integration/`. Add `pytestmark = pytest.mark.integration` at module level.
- Use `from conftest import make_egg` for test egg fixtures.
- Keep test function names short and descriptive (e.g. `test_redact_true`, not `test_redaction_with_redact_flag_set_to_true_produces_secrets`).

## Code style

We use [Ruff](https://docs.astral.sh/ruff/) for formatting and linting:

```bash
make fmt     # auto-format + auto-fix
make check   # CI-style check (no writes)
```

Rules: `E`, `F`, `I`, `UP` (pyflakes, pycodestyle, isort, pyupgrade). Line length: 100. Target: Python 3.10.

## Adding a new connector

To add support for a new agent platform (e.g. `myagent`):

1. Create `pynydus/agents/myagent/` with `spawner.py` and `hatcher.py`
2. Implement `MyAgentSpawner.parse(files: dict[str, str]) -> ParseResult`
3. Implement `MyAgentHatcher.render(egg: Egg) -> RenderResult`
4. Add `MYAGENT = "myagent"` to `AgentType` in `pynydus/common/enums.py`
5. Register in `_get_spawner()` (`engine/pipeline.py`) and `_get_hatcher()` (`engine/hatcher.py`)
6. Add `Nydusfile.default` in the agent directory
7. Add unit tests in `tests/unit/test_myagent_connector.py`
8. Add the new agent type to the portability matrix in `tests/integration/test_portability.py`

See `docs/advanced/connectors.md` for the full connector architecture guide.

## Building base eggs

Base egg source definitions live in `pynydus/eggs/base/<agent>/<version>/`. Each directory contains a `Nydusfile` and the agent source files. Build them with:

```bash
make base-eggs
```

Output goes to `dist/base_eggs/<agent>/base.egg`.

## Building docs

Sphinx pulls the full public API from `pynydus/` via **sphinx-autodoc2** into
`docs/apidocs/`. Curated overviews live under `docs/api/` (client, schemas,
errors, etc.) and link into that tree.

```bash
uv sync --group docs
make docs
# Open docs/_build/index.html
```
