# Adding Connectors

pynydus is designed for extensibility. Adding support for a new source format or
target framework requires implementing one spawner, one hatcher, or both.

## Architecture

Nydus separates source reading from target rendering:

- **Spawners** are target-agnostic. They receive pre-redacted file contents
  and produce a `ParseResult` containing raw skills and memory records.
- **Hatchers** are source-agnostic. They receive a full `Egg` and render it
  into a `dict[str, str]` of target file contents (with placeholders intact).

```text
pynydus/agents/
  openclaw/
    spawner.py        # OpenClawSpawner
    hatcher.py        # OpenClawHatcher
    README.md
  zeroclaw/
    spawner.py        # ZeroClawSpawner
    hatcher.py        # ZeroClawHatcher
    README.md
  letta/
    spawner.py        # LettaSpawner
    hatcher.py        # LettaHatcher
    README.md
```

## Adding a new source (spawner)

Create a directory at `pynydus/agents/<name>/` with a `spawner.py`.
Implement three methods and a `FILE_PATTERNS` list:

```python
from pathlib import Path
from pynydus.api.raw_types import ParseResult, RawMemory, RawSkill
from pynydus.api.schemas import MemoryLabel, ValidationIssue, ValidationReport


class SlackSpawner:
    """Parse Slack export archives into Egg records."""

    FILE_PATTERNS = ["channels.json", "*.json"]

    def detect(self, input_path: Path) -> bool:
        """Return True if input_path looks like a Slack export."""
        return (input_path / "channels.json").exists()

    def parse(self, files: dict[str, str]) -> ParseResult:
        """Parse pre-redacted file contents into structured records.

        The pipeline handles file reading, credential scanning, and PII
        redaction before calling this method. `files` contains only
        placeholder tokens, never real secrets or PII.
        """
        skills: list[RawSkill] = []
        memories: list[RawMemory] = []

        for fname, content in files.items():
            if fname == "channels.json":
                memories.append(RawMemory(
                    text=content,
                    label=MemoryLabel.STATE,
                    source_file=fname,
                ))

        return ParseResult(skills=skills, memory=memories)

    def validate(self, input_path: Path) -> ValidationReport:
        """Validate the source before spawning."""
        issues: list[ValidationIssue] = []
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

### Spawner interface

| Method | Purpose |
|--------|---------|
| `detect(input_path)` | Return `True` if the path matches this framework's layout |
| `parse(files)` | Convert pre-redacted file contents into `ParseResult` |
| `validate(input_path)` | Check that the source is well-formed before spawning |
| `FILE_PATTERNS` | Glob patterns for files the pipeline should read |

### Register the spawner

1. Add a value to the `SourceType` enum in `pynydus/api/schemas.py`:

   ```python
   SLACK = "slack"
   ```

2. Add a case to `_get_spawner()` in `pynydus/engine/pipeline.py`

The Nydusfile parser automatically derives valid source types from
`SourceType`, so `SOURCE slack ./export/` works immediately with no other
changes. The new source works with every existing hatcher.

## Adding a new target (hatcher)

Create `pynydus/agents/<name>/hatcher.py`. Implement `render()` and
optionally `validate()`:

```python
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import Egg, ValidationIssue, ValidationReport


class NewTargetHatcher:
    """Render an Egg into NewTarget's native format."""

    def render(self, egg: Egg) -> RenderResult:
        """Map Egg records into target file contents.

        Returns a dict of filename -> content. Secret placeholders
        ({{SECRET_NNN}}) stay intact. The pipeline handles substitution
        and disk I/O.
        """
        files: dict[str, str] = {}

        for mem in egg.memory.memory:
            if mem.label == "persona":
                files["identity.md"] = mem.text
            elif mem.label == "flow":
                files["instructions.md"] = mem.text

        for skill in egg.skills.skills:
            files[f"tools/{skill.slug}.py"] = skill.content

        return RenderResult(files=files)

    def validate(self, egg: Egg) -> ValidationReport:
        """Check that this Egg can be hatched into NewTarget."""
        issues: list[ValidationIssue] = []
        if not egg.skills.skills:
            issues.append(ValidationIssue(
                level="warning",
                message="No skills. Agent will have no capabilities.",
            ))
        return ValidationReport(
            valid=not any(i.level == "error" for i in issues),
            issues=issues,
        )
```

### Hatcher interface

| Method | Purpose |
|--------|---------|
| `render(egg)` | Convert Egg records into a dict of file paths to file contents |
| `validate(egg)` | Check that the Egg is compatible with this target |

### Register the hatcher

1. Add a case to `_get_hatcher()` in `pynydus/engine/hatcher.py`

The new target is immediately available for all existing sources.

## Key types

### For spawner authors

| Type | Module | Purpose |
|------|--------|---------|
| `ParseResult` | `pynydus.api.raw_types` | Structured output from `parse()` |
| `RawSkill` | `pynydus.api.raw_types` | One skill: name + content |
| `RawMemory` | `pynydus.api.raw_types` | One memory snippet: text + label + source_file |
| `MemoryLabel` | `pynydus.api.schemas` | Enum: `persona`, `flow`, `context`, `state` |
| `ValidationReport` | `pynydus.api.schemas` | Validation result with issues list |

### For hatcher authors

| Type | Module | Purpose |
|------|--------|---------|
| `RenderResult` | `pynydus.api.raw_types` | Dict of filename to file content |
| `Egg` | `pynydus.api.schemas` | The full Egg with all modules |
| `SkillRecord` | `pynydus.api.schemas` | Typed skill with ID and metadata |
| `MemoryRecord` | `pynydus.api.schemas` | Typed memory with label and skill_ref |
| `SecretRecord` | `pynydus.api.schemas` | Placeholder with kind and occurrences |

## Testing

Add tests in `tests/test_<name>.py`. The existing connector tests
(`test_openclaw.py`, `test_zeroclaw.py`, `test_letta_spawner.py`) are good
templates. At minimum, test:

- `detect()` returns `True` for valid inputs and `False` for others
- `parse()` produces the expected records from sample files
- `validate()` catches structural problems
- Round-trip: spawn from source, hatch into the same target, verify output
