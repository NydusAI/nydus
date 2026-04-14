# Code Style

Rules for docstrings, comments, formatting, and lint in the `pynydus/` tree.
Humans and automation should follow these conventions.

## Typography

Avoid these in docstrings, `#` comments, Markdown prose meant for readers, or
user-visible runtime strings (CLI output, raised errors, log messages to humans):

- **Em dash** (Unicode U+2014). Prefer a colon (label: explanation), a comma,
  parentheses, or two short sentences.
- **Semicolon** (`;`) to join clauses. Use a period, comma, or parentheses.
  Google-style `Args:` lines use a colon after the parameter name only. Do not
  chain clauses with `;` inside descriptions.

Do not change semicolons required by Python syntax or by wire-format literals
that must match an external protocol. When joining human-readable fragments, use
` | ` or newlines instead of `"; "`.

## Docstring style: Google

Use [Google-style docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
for all modules, classes, and functions.

### Module-level docstrings

Every `.py` file must start with a module docstring. State what the module
does, not what it contains. If the module implements a multi-step process, list
the steps.

```python
"""Hatching pipeline: transforms an Egg into a target runtime.

Two modes:
  rebuild     (default): render from structured egg modules via connector
  passthrough           replay redacted raw/ snapshot verbatim

Pipeline steps:
    1. Version check
    2. Build file dict
    3. LLM polish
    4. Secrets IN
    5. Write to disk
    6. Hatch log
"""
```

### Function and method docstrings

Every public function, every private function longer than about five lines, and
every method on a public class must have a docstring.

**Required sections** (include only those that apply):

| Section      | When to include                              |
|--------------|----------------------------------------------|
| Summary line | Always. One imperative sentence.             |
| Args         | Any function with parameters beyond `self`.  |
| Returns      | Any function that returns a non-None value.  |
| Raises       | Any function that intentionally raises.      |

**Format:**

```python
def refine_hatch(
    file_dict: dict[str, str],
    egg: Egg,
    llm_config: LLMTierConfig,
    *,
    log: list[dict] | None = None,
) -> dict[str, str]:
    """Adapt reconstructed files for the target platform via LLM.

    Sends each file through the configured LLM tier for polishing or
    cross-platform adaptation. Retries up to REFINEMENT_RETRY_LIMIT
    times if redaction placeholders are dropped, and falls back to the
    original content when all attempts fail.

    Args:
        file_dict: Mapping of filename to file content (placeholder'd).
        egg: The Egg being hatched (provides manifest and secrets list).
        llm_config: LLM provider, model, and API key.
        log: If set, hatch log entries are appended here.

    Returns:
        Updated file dict. Files whose placeholders could not be
        preserved are returned unchanged.
    """
```

**Bad (do not do this):**

```python
def refine_skills(skills, llm_config, spawn_log=None):
    """Standalone skill refinement: delegates to _refine_skills via EggPartial."""
```

This restates internal wiring. It tells the caller nothing about what the
function does, what it expects, or what it returns.

### Class docstrings

One-line summary of purpose. If the class has important invariants or
lifecycle notes, add them after the summary.

```python
class PipelineContext:
    """Mutable state threaded through each spawn pipeline step.

    All Nydusfile fields are front-loaded here at construction time.
    No step should reach back into NydusfileConfig after this point.
    """
```

### Docstrings for trivial functions

Functions that are genuinely one-line (e.g. a property, a thin wrapper)
can use a single-line docstring. Do not pad with empty Args/Returns
sections when the signature is self-documenting:

```python
def _extract_placeholders(text: str) -> set[str]:
    """Return all {{SECRET_NNN}} / {{PII_NNN}} tokens in *text*."""
    return set(_PLACEHOLDER_RE.findall(text))
```

## In-function comments

### When to comment

Comment **why**, not **what**. The code already says what it does. A comment
should explain:

- Non-obvious intent or constraints ("we check version compat before any
  file I/O so we fail fast on stale eggs")
- Domain rules that are not obvious from the code ("the LLM never sees real
  secrets: only placeholder tokens")
- Security boundaries ("secrets IN is the last transform before disk. Nothing
  after this point should touch file content")
- The reason for a specific ordering or grouping
- Edge cases and gotchas ("Pydantic model_copy creates a shallow copy of
  lists, so we extend the caller's spawn_log explicitly")

### When NOT to comment

Do not write comments that narrate the code:

```python
# BAD: restates the code
secret_counter = 1  # Initialize secret counter to 1

# BAD: obvious from the function name
group_files = _filter_files_by_patterns(group_files, patterns)  # Filter files

# BAD: labels a block that is already self-explanatory
url = url.rstrip("/")  # Strip trailing slash for clean URL joining
```

### Step comments in pipelines

When a function implements a numbered pipeline (spawn steps 1-10, hatch
steps 1-7), use step-header comments to mark boundaries. These are
**structural**, not narrating. Keep them short and match the documented
step names:

```python
# --- Step 3: Redaction (secret scan + PII) ---
```

After the header, add a brief "why" comment only if the step has
non-obvious behavior:

```python
# --- Step 4: Secrets IN (last transform before disk) ---
# Real values are injected here so the LLM never sees them.
if placeholder_map:
    file_dict = _substitute_secrets(file_dict, placeholder_map)
```

### Section separators

Use the project's existing separator style for grouping related functions:

```python
# ---------------------------------------------------------------------------
# Step 1 helpers: Base egg resolution
# ---------------------------------------------------------------------------
```

Do not over-section. One separator per logical group is enough. Do not add
a separator for a single function.

## Project-specific API expectations

- Every **module** needs a file-level docstring (what the module does).
- **`pynydus/`** and **`docs/conf.py`**: public functions with parameters need
  an **`Args:`** section (and `Returns:` / `Raises:` when applicable).
  **`tests/`** still need module docstrings but are not required to add `Args:`
  on every `test_*` function.
- **Private** helpers longer than about **eight** lines should have at least a
  one-line summary.
- Prefer **step headers** and short **why** comments at security boundaries.
  Avoid comments that only restate the next line of code.

## Formatting and lint

Local CI-style checks live in the repository root (the `nydus/` directory
that contains `Makefile`, `pynydus/`, and `tests/`).

### `make check`

Runs **Ruff** format check and lint on `pynydus/` and `tests/`. There are
no writes. Use `make fmt` to auto-format and apply safe Ruff fixes.

### Ruff

Rules: `E`, `F`, `I`, `UP` (pyflakes, pycodestyle, isort, pyupgrade). Line
length: 100. Target: Python 3.10.

Run manually:

```bash
uv run ruff format --check pynydus tests
uv run ruff check pynydus tests
```