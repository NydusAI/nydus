# Raw Types

Types used at the boundary between framework-specific connectors and the core
pipeline. Spawners produce `ParseResult` objects. Hatchers produce
`RenderResult` objects.

These types live in `pynydus.api.raw_types`.

## Spawner output

When building a new spawner, your `parse()` method receives a dict of
pre-redacted file contents and returns a `ParseResult`:

```python
from pynydus.api.raw_types import ParseResult, RawSkill, RawMemory
from pynydus.api.schemas import MemoryLabel

def parse(self, files: dict[str, str]) -> ParseResult:
    return ParseResult(
        skills=[
            RawSkill(name="order-lookup", content="Given an order ID..."),
        ],
        memory=[
            RawMemory(
                text="I am Maya, a customer support agent.",
                label=MemoryLabel.PERSONA,
                source_file="SOUL.md",
            ),
        ],
    )
```

### ParseResult

The structured output of a spawner's `parse()` method. Contains lists of raw
skills and raw memory records, plus optional metadata like MCP configs and
source metadata dicts.

```{autodoc2-object} pynydus.api.raw_types.ParseResult
```

### RawSkill

A single skill extracted from source files. Contains a name and the raw content
string. The pipeline later wraps this into a full `SkillRecord` with a stable
ID and Agent Skills formatting.

```{autodoc2-object} pynydus.api.raw_types.RawSkill
```

### RawMemory

A single memory snippet extracted from source files. Contains the text, an
optional `MemoryLabel`, and the source file path for provenance. The pipeline
promotes this into a `MemoryRecord` with a stable ID and timestamp.

```{autodoc2-object} pynydus.api.raw_types.RawMemory
```

## Hatcher output

When building a new hatcher, your `render()` method receives an `Egg` and
returns a `RenderResult`:

```python
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import Egg

def render(self, egg: Egg) -> RenderResult:
    files = {}
    for mem in egg.memory.memory:
        if mem.label == "persona":
            files["persona.md"] = mem.text
    return RenderResult(files=files)
```

### RenderResult

The output of a hatcher's `render()` method. A dict mapping relative file paths
to file contents. Secret placeholders (`{{SECRET_NNN}}`) remain in the content
at this stage. The pipeline handles substitution and disk I/O.

```{autodoc2-object} pynydus.api.raw_types.RenderResult
```
