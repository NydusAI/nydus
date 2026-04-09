# Adding New Connectors

PyNydus is designed for extensibility. Adding support for a new framework
requires implementing a single file with a small interface.

## Architecture


Nydus separates source reading (spawners) from target rendering (hatchers):

- **Spawners** are target-agnostic: `parse(files) -> ParseResult`
- **Hatchers** are target-specific: `render(egg) -> RenderResult`


```text
agents/
  openclaw/
    spawner.py
    hatcher.py
  letta/
    spawner.py
    hatcher.py
  zeroclaw/
    spawner.py
    hatcher.py
```

## Adding a new source


Create `pynydus/agents/slack/spawner.py` with `detect()`, `parse()`,
`validate()`, and `FILE_PATTERNS`:

```python
from pathlib import Path
from pynydus.api.raw_types import ParseResult, RawMemory, RawSkill
from pynydus.api.schemas import ValidationIssue, ValidationReport
from pynydus.common.enums import MemoryLabel


class SlackSpawner:
    """Parse Slack export archives."""

    FILE_PATTERNS = ["channels.json", "*.json"]

    def detect(self, input_path: Path) -> bool:
        return (input_path / "channels.json").exists()

    def parse(self, files: dict[str, str]) -> ParseResult:
        """Receives pre-redacted file contents. Never sees real secrets."""
        skills = []
        memories = []
        # ... parsing logic ...
        return ParseResult(skills=skills, memory=memories)

    def validate(self, input_path: Path) -> ValidationReport:
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


Then register:

1. Add `SLACK = "slack"` to `AgentType` in `pynydus/common/enums.py`
2. Add a case to `_get_spawner()` in `pynydus/engine/pipeline.py`

The new source is immediately available for all targets.

## Adding a new target


Create `pynydus/agents/newtarget/hatcher.py`:

```python
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import Egg, ValidationIssue, ValidationReport


class NewTargetHatcher:
    def render(self, egg: Egg) -> RenderResult:
        """Returns dict of filename -> content with placeholders intact."""
        files = {}
        for skill in egg.skills.skills:
            pass  # convert to target format
        for mem in egg.memory.memory:
            pass  # convert to target format
        return RenderResult(files=files)

    def validate(self, egg: Egg) -> ValidationReport:
        issues = []
        if not egg.skills.skills:
            issues.append(ValidationIssue(
                level="warning",
                message="No skills. Agent will have no capabilities",
            ))
        return ValidationReport(
            valid=not any(i.level == "error" for i in issues),
            issues=issues,
        )
```


Register: add a case to `_get_hatcher()` in `pynydus/engine/hatcher.py`.

## Key types


**Spawner types** (`pynydus.api.raw_types`):
- {py:class}`~pynydus.api.raw_types.ParseResult`: output from `parse()`
- {py:class}`~pynydus.api.raw_types.RawSkill`: one skill (name + content)
- {py:class}`~pynydus.api.raw_types.RawMemory`: one memory snippet


**Hatcher types**:
- {py:class}`~pynydus.api.raw_types.RenderResult`: output from `render()`
- {py:class}`~pynydus.api.schemas.Egg`: the full Egg
- {py:class}`~pynydus.api.schemas.SkillRecord`, {py:class}`~pynydus.api.schemas.MemoryRecord`, {py:class}`~pynydus.api.schemas.SecretRecord`
