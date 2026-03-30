"""Data types for spawner/hatcher interfaces and the pipeline.

- ``ParseResult`` — output of ``spawner.parse()``, structured records from redacted files.
- ``RenderResult`` — output of ``hatcher.render()``, target file contents with placeholders.
- ``RawSkill`` / ``RawMemory`` — individual records within ParseResult.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from pynydus.api.schemas import MemoryLabel


class RawSkill(BaseModel):
    """A skill extracted verbatim from a source platform."""

    name: str
    content: str
    source_file: str | None = None


class RawMemory(BaseModel):
    """A single memory snippet extracted from a source platform."""

    text: str
    source_file: str | None = None
    label: MemoryLabel | None = None
    """Optional label hint from the spawner (e.g. MemoryLabel.PERSONA)."""
    timestamp: datetime | None = None
    """Optional timestamp from source data."""
    skill_ref: str | None = None
    """Optional reference to a skill name this memory is associated with."""



class ParseResult(BaseModel):
    """Output of ``spawner.parse()`` — structured records from redacted files.

    Spawners produce this after receiving pre-redacted file contents.
    No secrets, no raw_artifacts, no source_type — those are pipeline concerns.
    """

    skills: list[RawSkill] = Field(default_factory=list)
    memory: list[RawMemory] = Field(default_factory=list)
    mcp_configs: dict[str, dict] = Field(default_factory=dict)
    """MCP server configs discovered during parsing, keyed by server name."""
    source_metadata: dict[str, str] = Field(default_factory=dict)


class RenderResult(BaseModel):
    """Output of ``hatcher.render()`` — target file contents from Egg records.

    Hatchers produce this from an Egg.  Files contain ``{{SECRET_NNN}}``
    and ``{{PII_NNN}}`` placeholders; the pipeline substitutes real values
    at the secrets-IN boundary.
    """

    files: dict[str, str] = Field(default_factory=dict)
    """Filename → UTF-8 content (with placeholders intact)."""
    warnings: list[str] = Field(default_factory=list)


