.PHONY: install dev lint fmt format check test test-unit test-integration test-live-llm cov docs build clean base-eggs

install:            ## Install dependencies
	uv sync

dev:                ## Install with dev dependencies
	uv sync --group dev

lint:               ## Same as check: format check + Ruff lint
	@$(MAKE) check

format:             ## Alias for fmt
	@$(MAKE) fmt

fmt:                ## Auto-format with Ruff, then fix lint where possible
	uv run ruff format pynydus tests
	uv run ruff check pynydus tests --fix

check:              ## CI-style: format check + lint (no writes)
	uv run ruff format --check pynydus tests
	uv run ruff check pynydus tests

test:               ## Run all tests (unit + integration, excludes live_llm)
	uv run pytest tests/unit tests/integration -m "not live_llm"

test-unit:          ## Run unit tests only (no integration or live_llm)
	uv run pytest tests/unit -m "not live_llm"

test-integration:   ## Run integration tests only (requires gitleaks)
	uv run pytest tests/integration

test-live-llm:      ## Run live LLM tests (requires NYDUS_LLM_TYPE + NYDUS_LLM_API_KEY)
	uv run pytest tests/unit -m "live_llm"

cov:                ## Run tests with coverage (excludes live_llm)
	uv run pytest tests/unit tests/integration -m "not live_llm" --cov --cov-report=html

docs:               ## Build Sphinx HTML (installs docs dependency group)
	uv sync --group docs
	cd docs && uv run sphinx-build -b html . _build

build:              ## Build package
	uv build

base-eggs:          ## Generate base eggs from declarative definitions
	cd pynydus/eggs/base/openclaw/0.0.1 && uv run nydus spawn -o ../../../../../dist/base_eggs/openclaw/base.egg
	cd pynydus/eggs/base/letta/0.0.1 && uv run nydus spawn -o ../../../../../dist/base_eggs/letta/base.egg
	cd pynydus/eggs/base/zeroclaw/0.0.1 && uv run nydus spawn -o ../../../../../dist/base_eggs/zeroclaw/base.egg

clean:              ## Remove build artifacts
	rm -rf dist/ .coverage coverage_html/ docs/_build/ .pytest_cache/ .ruff_cache/
