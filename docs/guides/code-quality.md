# Code quality checks

Local CI-style checks live in the **repository root** (the `nydus/` directory that contains `Makefile`, `pynydus/`, and `tests/`).

## `make check`

Runs **Ruff** format check and lint on `pynydus/` and `tests/`. There are no writes.
Use `make fmt` to auto-format and apply safe Ruff fixes.

Docstring, comment, and typography **conventions** for this project are documented
in {doc}`/contributing/code-style`. They are not enforced by a separate script in CI.

## Ruff

Rules: `E`, `F`, `I`, `UP` (pyflakes, pycodestyle, isort, pyupgrade). Line length:
100. Target: Python 3.10.

Run manually:

```bash
uv run ruff format --check pynydus tests
uv run ruff check pynydus tests
```

## Local-only files

Optional notes, scratch scripts, and other files you do not intend to push can
live under **`.internal/`** at the repository root (for example a personal
`COMMENT_RULES.md` pointer or a working copy of **`NEW_AGENTS.md`**). A tracked
**`.internal/.gitkeep`** keeps that folder in the tree; everything else under
`.internal/` is ignored via `.gitignore`.

## Checklist before you submit

- [ ] {doc}`/contributing/code-style` (docstrings, comments, typography)
- [ ] `make check` passes
