"""Pydantic models for the Egg data model.

Includes manifest, skills, memory, secrets modules, and the top-level ``Egg``
container types used in spawn/hatch/save.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from pynydus.api.skill_format import AgentSkill  # noqa: F401  # canonical skill type
from pynydus.common.enums import (  # noqa: F401  # re-exported for convenience
    AgentType,
    Bucket,
    DiffChange,
    HatchMode,
    InjectionMode,
    MemoryLabel,
    ModuleType,
    SecretKind,
)

# ---------------------------------------------------------------------------
# Module records / containers
# ---------------------------------------------------------------------------


class McpModule(BaseModel):
    """Raw MCP server configs. Nydus does not model MCP fields.

    Stored as ``mcp.json`` in the egg archive using Claude Desktop format
    (``{ "mcpServers": { "<name>": { ... } } }``).
    """

    configs: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SkillsModule(BaseModel):
    """Container for all skills in an Egg (agentskills.io format)."""

    skills: list[AgentSkill] = Field(default_factory=list)


class MemoryRecord(BaseModel):
    """A single memory record."""

    id: str
    text: str
    label: MemoryLabel
    agent_type: str
    source_store: str
    skill_ref: str | None = None
    timestamp: datetime | None = None
    shareable: bool = True


class MemoryModule(BaseModel):
    """Container for all memory records in an Egg."""

    memory: list[MemoryRecord] = Field(default_factory=list)


class SecretRecord(BaseModel):
    """A single redaction placeholder record (credential or PII). Spec §6.2."""

    id: str
    placeholder: str
    kind: SecretKind
    pii_type: str | None = None
    name: str
    required_at_hatch: bool = False
    injection_mode: InjectionMode = InjectionMode.ENV
    description: str = ""
    value_present: bool = False
    occurrences: list[str] = Field(default_factory=list)


class SecretsModule(BaseModel):
    """Container for all redaction placeholder records in an Egg."""

    secrets: list[SecretRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


class RedactionPolicy(BaseModel):
    """Records what redaction was applied during spawning."""

    pii_redacted: bool = True
    secrets_placeholder_only: bool = True


class SourceEntry(BaseModel):
    """The single SOURCE tree that contributed to this egg, if any."""

    agent_type: str
    source_path: str = ""


class Manifest(BaseModel):
    """Top-level Egg metadata."""

    nydus_version: str
    min_nydus_version: str = "0.0.7"
    egg_version: str = "1.0"
    created_at: datetime
    agent_type: AgentType
    signature: str = ""

    # Optional
    base_egg: str | None = None
    """Base egg reference this egg inherited from (e.g. 'nydus/openclaw:0.3.0')."""
    redaction_policy: RedactionPolicy | None = None

    # Neutral fields: any spawner writes, any hatcher reads
    agent_name: str | None = None
    agent_description: str | None = None
    llm_model: str | None = None
    llm_context_window: int | None = None
    embedding_model: str | None = None
    source_dir: str | None = None

    sources: Annotated[list[SourceEntry], Field(max_length=1)] = Field(default_factory=list)
    """At most one source entry (FROM-only spawns may omit this list)."""


# ---------------------------------------------------------------------------
# Egg
# ---------------------------------------------------------------------------


class Egg(BaseModel):
    """The canonical portable artifact.

    Redacted sources and spawn pipeline log align with ``raw/`` and
    ``spawn_log.json`` in the ``.egg`` archive. Use :func:`~pynydus.engine.packager.load`
    to populate these from disk, and :func:`~pynydus.engine.packager.save` to write them.
    """

    manifest: Manifest
    skills: SkillsModule = Field(default_factory=SkillsModule)
    mcp: McpModule = Field(default_factory=McpModule)
    memory: MemoryModule = Field(default_factory=MemoryModule)
    secrets: SecretsModule = Field(default_factory=SecretsModule)
    raw_artifacts: dict[str, str] = Field(default_factory=dict)
    """Redacted source snapshots (ZIP ``raw/…``)."""
    spawn_log: list[dict] = Field(default_factory=list)
    """Structured spawn pipeline events (ZIP ``spawn_log.json``)."""
    nydusfile: str | None = None
    """Embedded Nydusfile text when present in the archive (ZIP ``Nydusfile``)."""

    # Standard artifact fields (populated during spawn, optional for legacy eggs)
    a2a_card: dict[str, Any] | None = None
    """A2A agent card (agent-card.json)."""
    agents_md: str | None = None
    """Per-egg deployment runbook (AGENTS.md)."""
    apm_yml: str | None = None
    """Passthrough APM manifest from source project."""
    spec_snapshots: dict[str, str] | None = None
    """Embedded spec markdown snapshots keyed by standard name."""

    def inspect_secrets(self) -> list[dict]:
        """Return a summary of all secret placeholders and their occurrences.

        Returns:
            List of dicts with placeholder, name, kind, required, and occurrences.
        """
        return [
            {
                "placeholder": s.placeholder,
                "name": s.name,
                "kind": s.kind.value,
                "required": s.required_at_hatch,
                "occurrences": list(s.occurrences),
            }
            for s in self.secrets.secrets
        ]


# ---------------------------------------------------------------------------
# Pipeline types
# ---------------------------------------------------------------------------


class ValidationIssue(BaseModel):
    """A single validation finding (error or warning)."""

    level: Literal["error", "warning"]
    message: str
    location: str | None = None


class ValidationReport(BaseModel):
    """Result of validating an Egg or source input."""

    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class EggPartial(BaseModel):
    """Intermediate result from a spawner before full packaging."""

    skills: SkillsModule = Field(default_factory=SkillsModule)
    mcp: McpModule = Field(default_factory=McpModule)
    memory: MemoryModule = Field(default_factory=MemoryModule)
    secrets: SecretsModule = Field(default_factory=SecretsModule)
    raw_artifacts: dict[str, str] = Field(default_factory=dict)

    # Pipeline log: single list of typed events, packed into logs/spawn_log.json
    spawn_log: list[dict] = Field(default_factory=list)


class HatchResult(BaseModel):
    """Output from a hatcher."""

    target: AgentType
    output_dir: Path
    files_created: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    hatch_log: list[dict] = Field(default_factory=list)
    """Structured log entries produced during the hatch pipeline."""


class ManifestChange(BaseModel):
    """A single manifest-level field difference between two Eggs."""

    field: str
    """Which manifest field changed."""

    old: str | None = None
    """Old value (stringified)."""

    new: str | None = None
    """New value (stringified)."""


class DiffEntry(BaseModel):
    """A single record-level difference within a module type."""

    bucket: ModuleType
    """Which module the record belongs to (skill, memory, secret)."""

    change: DiffChange
    """Type of change: ADDED, REMOVED, or MODIFIED."""

    id: str | None = None
    """Record ID."""

    field: str | None = None
    """Which field changed (None for add/remove of whole records)."""

    old: str | None = None
    """Old value (stringified). None for additions."""

    new: str | None = None
    """New value (stringified). None for removals."""


class DiffReport(BaseModel):
    """Result of comparing two Eggs."""

    identical: bool
    manifest_changes: list[ManifestChange] = Field(default_factory=list)
    entries: list[DiffEntry] = Field(default_factory=list)
