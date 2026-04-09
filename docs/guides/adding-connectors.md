# Adding New Connectors

PyNydus is designed for extensibility. Adding support for a new framework
requires implementing a small interface and a platform specification.

## Architecture


Nydus separates source reading (spawners) from target rendering (hatchers):

- **Spawners** are target-agnostic: `parse(files) -> ParseResult`
- **Hatchers** are target-specific: `render(egg) -> RenderResult`


```text
agents/
  openclaw/
    spawner.py
    hatcher.py
    AGENT_SPEC.md
  letta/
    spawner.py
    hatcher.py
    AGENT_SPEC.md
  zeroclaw/
    spawner.py
    hatcher.py
    AGENT_SPEC.md
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
3. Create `pynydus/agents/slack/AGENT_SPEC.md` describing the platform's
   workspace conventions, file layout, and formatting rules (see existing
   specs for examples)

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


Register:

1. Add a case to `_get_hatcher()` in `pynydus/engine/hatcher.py`
2. Create `pynydus/agents/newtarget/AGENT_SPEC.md` so the hatch LLM can
   adapt output to the target platform's idioms. See {doc}`/guides/llm-refinement`
   for how specs are used during refinement.

## Platform specification (AGENT_SPEC.md)


Every connector directory must include an `AGENT_SPEC.md` file that describes
the platform's workspace conventions. At hatch time, Nydus loads the source and
target specs and injects them into the LLM prompt. Without a spec, LLM
refinement cannot adapt content to the platform's idioms.

The spec should cover:

- Required and optional files with their roles
- File naming conventions (e.g., uppercase vs. lowercase, extensions)
- Content format expectations (Markdown, TOML, JSON, Python)
- Directory structure and marker files
- Any platform-specific constraints

See the existing `AGENT_SPEC.md` files in `pynydus/agents/openclaw/`,
`pynydus/agents/letta/`, and `pynydus/agents/zeroclaw/` for examples.

## Key types


**Spawner types** (`pynydus.api.raw_types`):
- {py:class}`~pynydus.api.raw_types.ParseResult`: output from `parse()`
- {py:class}`~pynydus.api.raw_types.RawSkill`: one skill (name + content)
- {py:class}`~pynydus.api.raw_types.RawMemory`: one memory snippet


**Hatcher types**:
- {py:class}`~pynydus.api.raw_types.RenderResult`: output from `render()`
- {py:class}`~pynydus.api.schemas.Egg`: the full Egg
- {py:class}`~pynydus.api.schemas.SkillRecord`, {py:class}`~pynydus.api.schemas.MemoryRecord`, {py:class}`~pynydus.api.schemas.SecretRecord`
