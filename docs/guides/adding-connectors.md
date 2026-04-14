# Adding New Connectors

PyNydus is designed for extensibility. Adding support for a new framework
requires implementing a small interface and a platform specification.

## Architecture


Nydus separates source reading (spawners) from target rendering (hatchers):

- **Spawners** are target-agnostic: `parse(files) -> ParseResult` (subclass `Spawner` ABC)
- **Hatchers** are target-specific: `render(egg, output_dir) -> RenderResult` (subclass `Hatcher` ABC)


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


Create `pynydus/agents/slack/spawner.py` subclassing `Spawner`:

```python
from pynydus.api.protocols import Spawner
from pynydus.api.raw_types import ParseResult, RawMemory, RawSkill
from pynydus.common.enums import MemoryLabel


class SlackSpawner(Spawner):
    """Parse Slack export archives."""

    def parse(self, files: dict[str, str]) -> ParseResult:
        """Receives pre-redacted file contents. Never sees real secrets."""
        skills: list[RawSkill] = []
        memories: list[RawMemory] = []
        mcp_configs: dict[str, dict] = {}

        # Parse channels.json, messages, etc.
        # ...

        return ParseResult(
            skills=skills,
            memory=memories,
            mcp_configs=mcp_configs,
            agent_name="my-slack-agent",
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


Create `pynydus/agents/newtarget/hatcher.py` subclassing `Hatcher`:

```python
from pathlib import Path

from pynydus.api.protocols import Hatcher
from pynydus.api.raw_types import RenderResult
from pynydus.api.schemas import Egg


class NewTargetHatcher(Hatcher):
    def render(self, egg: Egg, output_dir: Path) -> RenderResult:
        """Returns dict of filename -> content with placeholders intact."""
        files: dict[str, str] = {}
        for skill in egg.skills.skills:
            pass  # convert to target format
        for mem in egg.memory.memory:
            pass  # convert to target format

        # MCP configs (Claude Desktop format)
        if egg.mcp.configs:
            import json
            files["mcp.json"] = json.dumps(
                {"mcpServers": egg.mcp.configs}, indent=2
            )

        return RenderResult(files=files)
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


**Protocols** (`pynydus.api.protocols`):
- {py:class}`~pynydus.api.protocols.Spawner`: ABC — implement `parse(files) -> ParseResult`
- {py:class}`~pynydus.api.protocols.Hatcher`: ABC — implement `render(egg, output_dir) -> RenderResult`


**Spawner types** (`pynydus.api.raw_types`):
- {py:class}`~pynydus.api.raw_types.ParseResult`: output from `parse()`
- {py:class}`~pynydus.api.raw_types.RawSkill`: one skill (name + content)
- {py:class}`~pynydus.api.raw_types.RawMemory`: one memory snippet


**Hatcher types**:
- {py:class}`~pynydus.api.raw_types.RenderResult`: output from `render()`
- {py:class}`~pynydus.api.schemas.Egg`: the full Egg
- {py:class}`~pynydus.api.skill_format.AgentSkill`, {py:class}`~pynydus.api.schemas.MemoryRecord`, {py:class}`~pynydus.api.schemas.SecretRecord`
