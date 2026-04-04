# Connectors

Spawners and hatchers map framework-specific files to the canonical Egg model
and back. Implementation: `pynydus/agents/<name>/spawner.py` and `hatcher.py`.

## Source connectors (spawners)

Spawners implement a `parse(files: dict[str, str]) -> ParseResult` method that
receives pre-redacted file contents and returns structured `RawSkill` and
`RawMemory` lists. The pipeline handles file reading, **gitleaks** secret scanning,
then **Presidio** PII redaction, before calling `parse()`.

### OpenClaw (`agents/openclaw/spawner.py`)

| Source file | Becomes | Notes |
|-------------|---------|-------|
| `SOUL.md` / `soul.md` / `IDENTITY.md` | `RawMemory`, label **persona** | Split by paragraphs |
| `AGENTS.md` / `agents.md` / `BOOT.md` / `HEARTBEAT.md` | `RawMemory`, label **flow** | Split by paragraphs |
| `USER.md` / `user.md` / `TOOLS.md` | `RawMemory`, label **context** | Split by paragraphs |
| `knowledge.md` / `MEMORY.md` / `memory/*.md` | `RawMemory`, label **state** | Split by paragraphs. Date extracted from `memory/YYYY-MM-DD.md` filenames |
| `skill.md` / `skills.md` | `RawSkill` per heading | Split by `# ...` headings |
| `skills/*.md` | `RawSkill` per file | Filename stem → display name |
| `config.yaml` / `config.yml` / `config.json` | `SecretRecord` (from spawn: gitleaks) | Detected as secrets by gitleaks on file text; not a spawner keyword heuristic |
| `mcp.json` / `mcp/*.json` | MCP configs | Parsed JSON per server |
| All text files | `raw_artifacts` | Full text keyed by relative path |

**Detection:** directory with any persona file (`SOUL.md`, `soul.md`,
`IDENTITY.md`) or `skill.md` / `skills.md` / `skills/`.

### Letta (`agents/letta/spawner.py`)

| Source | Becomes | Notes |
|--------|---------|-------|
| `tools/*.py` | `RawSkill` | Filename stem → display name |
| `agent_state.json` → `tools[]` | Extra `RawSkill` | From `source_code` field |
| `agent_state.json` → `system` | `RawMemory`, **flow** | |
| `agent_state.json` → `memory` blocks | `RawMemory` per block | `persona` → **persona**, `human` → **context**, `system` → **flow** |
| `system_prompt.md` / `.txt` | `RawMemory`, **flow** | Fallback if not in `agent_state.json` |
| `archival_memory.json` | `RawMemory`, **state** | Array of `{text, timestamp?}` |
| `archival/*.{txt,md,json}` | `RawMemory`, **state** | |
| Config files | `SecretRecord` (from spawn: gitleaks) | Same pipeline secret scan as other text files |
| `agent.db` (SQLite) | Skills + memory + secrets | Tables: `blocks`, `archival_memory`, `tools`, `agents` |

**Detection:** `.letta/` directory, `agent_state.json`, `agent.db`, or
`tools/*.py`.

### ZeroClaw (`agents/zeroclaw/spawner.py`)

| Source | Becomes | Notes |
|--------|---------|-------|
| `SOUL.md` / `persona.md` / `IDENTITY.md` | `RawMemory`, **persona** | Split by paragraphs |
| `AGENTS.md` / `agents.md` / `instructions.md` / `system_prompt.md` / `HEARTBEAT.md` | `RawMemory`, **flow** | Split by paragraphs |
| `USER.md` / `user.md` / `context.md` / `TOOLS.md` | `RawMemory`, **context** | Split by paragraphs |
| `MEMORY.md` / `knowledge.md` / `memory/*.md` | `RawMemory`, **state** | Split by paragraphs. Date extracted from `memory/YYYY-MM-DD.md` filenames |
| `tools/*.py` | `RawSkill` | Filename stem → name |
| `tools.json` | `RawSkill` | List of `{name, source/description}` |
| `config.json` / `config.yaml` / `config.yml` | `SecretRecord` (from spawn: gitleaks) | |
| `mcp.json` / `mcp/*.json` | MCP configs | |

**Detection:** `.zeroclaw/` marker, or any persona file (`SOUL.md`,
`persona.md`, `IDENTITY.md`), or `tools/`/`tools.json`, or `AGENTS.md`.

## Target connectors (hatchers)

Hatchers implement a `render(egg: Egg) -> RenderResult` method that produces an
in-memory dict of target file contents with placeholders intact. The pipeline
optionally runs LLM refinement (on placeholder'd content), then substitutes
secrets, and writes the files to disk. All 4 `MemoryLabel` values have explicit
file mappings in every hatcher. No fallback or unmapped labels.

### OpenClaw (`agents/openclaw/hatcher.py`)

| Egg content | Output file |
|-------------|-------------|
| Memory label **persona** | `soul.md` |
| Memory label **flow** | `agents.md` |
| Memory label **context** | `user.md` |
| Memory label **state** | `knowledge.md` |
| All skills | `skill.md` (each skill as `# {name}`) |
| Credential secrets | `config.json` |
| MCP configs | `mcp/<name>.json` |

### Letta (`agents/letta/hatcher.py`)

| Egg content | Output |
|-------------|--------|
| **persona** | `agent_state.json` → `memory.persona.value` |
| **context** | `agent_state.json` → `memory.human.value` |
| **flow** | `agent_state.json` → `system` + `system_prompt.md` |
| **state** | `archival_memory.json` |
| Skills | `tools/<slug>.py` + `agent_state.json` tool refs |
| Credential secrets | `.letta/config.json` |

### ZeroClaw (`agents/zeroclaw/hatcher.py`)

| Egg content | Output |
|-------------|--------|
| **persona** | `persona.md` |
| **flow** | `agents.md` |
| **context** | `user.md` |
| **state** | `knowledge.md` |
| Skills | `tools/<slug>.py` |
| Credential secrets | `config.json` |
| MCP configs | `mcp/<name>.json` |

---

# Adding new connectors

PyNydus is designed for extensibility. Adding support for a new source format or
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

        The pipeline handles file reading, gitleaks secret scanning, and PII
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

1. Add `SLACK = "slack"` to the `AgentType` enum in `pynydus/common/enums.py`
2. Add a case to `_get_spawner()` in `pynydus/engine/pipeline.py`

The Nydusfile parser automatically derives valid agent types from `AgentType`,
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
