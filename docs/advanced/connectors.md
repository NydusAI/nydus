# Adding Connectors

Nydus is designed for extensibility. Adding support for a new source format or
target framework requires implementing a single file with a small interface.

## Architecture

Nydus separates source reading (spawners) from target rendering (hatchers):

- **Spawners** are target-agnostic. They receive pre-redacted file contents
  and produce a `ParseResult`.
- **Hatchers** are target-specific. They render an Egg into an in-memory
  `dict[str, str]` of file contents (with placeholders).

```text
agents/                   # one directory per framework
  openclaw/
    spawner.py
    hatcher.py
    README.md
  letta/
    spawner.py
    hatcher.py
    README.md
  zeroclaw/
    spawner.py
    hatcher.py
    README.md
```

## Adding a new source

Create a new directory: `pynydus/agents/slack/` with a `spawner.py`. Implement
`detect()`, `parse()`, and `validate()` methods, plus a `FILE_PATTERNS` list:

```python
from pathlib import Path
from pynydus.api.raw_types import ParseResult, RawMemory, RawSkill
from pynydus.api.schemas import MemoryLabel, ValidationIssue, ValidationReport


class SlackSpawner:
    """Parse Slack export archives."""

    FILE_PATTERNS = ["channels.json", "*.json"]

    def detect(self, input_path: Path) -> bool:
        """Return True if input_path looks like a Slack export."""
        return (input_path / "channels.json").exists()

    def parse(self, files: dict[str, str]) -> ParseResult:
        """Parse pre-redacted file contents into structured records.

        The pipeline handles file reading, credential scanning, and PII
        redaction before calling this method. `files` only contains
        placeholder tokens, never real secrets or PII.
        """
        skills = []  # extract any workflow automations
        memories = []  # extract messages as memory records

        # ... parsing logic ...

        return ParseResult(
            skills=skills,
            memory=memories,
        )

    def validate(self, input_path: Path) -> ValidationReport:
        """Validate a Slack export before spawning."""
        issues = []
        if not (input_path / "channels.json").exists():
            issues.append(ValidationIssue(
                level="error",
                message="Missing channels.json",
                location=str(input_path),
            ))
        return ValidationReport(
            valid=not any(i.level == "error" for i in issues),
            issues=issues,
        )
```

Then register the spawner:

1. Add `SLACK = "slack"` to the `SourceType` enum in `pynydus/api/schemas.py`
2. Add a case to `_get_spawner()` in `pynydus/engine/pipeline.py`

The Nydusfile parser automatically derives valid source types from `SourceType`,
so no other changes are needed. The new source is immediately available for all
targets. No changes are needed in any hatcher.

## Adding a new target

Create one directory: `pynydus/agents/newtarget/` with `hatcher.py` and
optionally `base.egg`.

The hatcher must implement `render()` and optionally `validate()`:

```python
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import Egg, ValidationIssue, ValidationReport


class NewTargetHatcher:
    """Render an Egg into NewTarget's native format."""

    def render(self, egg: Egg) -> RenderResult:
        """Render Egg records into target file contents.

        Returns a dict of filename -> content with {{SECRET_NNN}} and
        {{PII_NNN}} placeholders intact. The pipeline handles secret
        substitution and disk I/O.
        """
        files = {}

        for skill in egg.skills.skills:
            # ... convert to target format ...
            pass

        for mem in egg.memory.memory:
            # ... convert to target format ...
            pass

        return RenderResult(files=files)

    def validate(self, egg: Egg) -> ValidationReport:
        """Validate that this Egg can be hatched into NewTarget."""
        issues = []
        if not egg.skills.skills:
            issues.append(ValidationIssue(
                level="warning",
                message="No skills. NewTarget agent will have no capabilities",
            ))
        return ValidationReport(
            valid=not any(i.level == "error" for i in issues),
            issues=issues,
        )
```

Then register the hatcher:

1. Add a case to `_get_hatcher()` in `pynydus/engine/hatcher.py`
2. Optionally generate a `base.egg` for use with FROM directives

The new target is immediately available for all sources.

## Key types

Spawner authors work with these types from `pynydus.api.raw_types`:

- {py:class}`~pynydus.api.raw_types.ParseResult`: structured output from `parse()`
- {py:class}`~pynydus.api.raw_types.RawSkill`: one skill (name + content)
- {py:class}`~pynydus.api.raw_types.RawMemory`: one memory snippet (text + optional label)

Hatcher authors work with these types:

- {py:class}`~pynydus.api.raw_types.RenderResult`: output from `render()`
- {py:class}`~pynydus.api.schemas.Egg`: the full Egg
- {py:class}`~pynydus.api.schemas.SkillRecord`: typed skill with ID and metadata
- {py:class}`~pynydus.api.schemas.MemoryRecord`: typed memory with label and skill_ref
- {py:class}`~pynydus.api.schemas.SecretRecord`: placeholder with occurrences
