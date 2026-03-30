.PHONY: install dev lint fmt test cov docs build clean base-eggs

install:            ## Install dependencies
	uv sync

dev:                ## Install with dev dependencies
	uv sync --group dev

lint:               ## Lint and format check
	uv run ruff check .
	uv run ruff format --check .

fmt:                ## Auto-format
	uv run ruff format .
	uv run ruff check --fix .

test:               ## Run tests
	uv run pytest

cov:                ## Run tests with coverage
	uv run pytest --cov --cov-report=html

docs:               ## Build Sphinx docs
	cd docs && uv run sphinx-build -b html . _build

build:              ## Build package
	uv build

base-eggs:          ## Generate base eggs from declarative definitions
	cd base_eggs/openclaw && uv run nydus spawn -o ../../dist/base_eggs/openclaw/base.egg
	cd base_eggs/letta && uv run nydus spawn -o ../../dist/base_eggs/letta/base.egg

clean:              ## Remove build artifacts
	rm -rf dist/ .coverage coverage_html/ docs/_build/ .pytest_cache/ .ruff_cache/
