"""Pydantic models for the Egg data model.

Covers: Manifest (§7), Skills (§5.1), Memory (§5.2), Secrets (§6.2), Egg container.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, computed_field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SourceType(StrEnum):
    """Supported source formats for spawning."""

    OPENCLAW = "openclaw"
    ZEROCLAW = "zeroclaw"
    LETTA = "letta"


class Bucket(StrEnum):
    """Top-level module buckets in an Egg."""

    SKILLS = "skills"
    MEMORY = "memory"
    SECRETS = "secrets"


class RedactMode(StrEnum):
    """PII/secret redaction modes for the spawning pipeline."""

    PII = "pii"
    SECRETS = "secrets"
    ALL = "all"
    NONE = "none"


class SecretKind(StrEnum):
    """Classification of a secret record: API credential or redacted PII."""

    CREDENTIAL = "credential"
    PII = "pii"


class InjectionMode(StrEnum):
    """How a secret value is provided at hatch time."""

    ENV = "env"
    CLI_PROMPT = "cli_prompt"
    CONFIG_FILE = "config_file"
    VAULT_REFERENCE = "vault_reference"
    SUBSTITUTION = "substitution"


class PriorityHint(StrEnum):
    """Soft hints from the PRIORITIZE Nydusfile directive."""

    RECENT_HISTORY = "recent_history"
    SKILLS = "skills"
    COMPACT_MEMORY = "compact_memory"


class MemoryLabel(StrEnum):
    """Canonical labels for memory records, assigned by spawners."""

    PERSONA = "persona"
    FLOW = "flow"
    CONTEXT = "context"
    STATE = "state"


# ---------------------------------------------------------------------------
# Module records
# ---------------------------------------------------------------------------


class SkillRecord(BaseModel):
    """A single skill extracted from the source. Spec §5.1."""

    id: str
    name: str
    source_type: str
    content: str
    attachments: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class McpServerConfig(BaseModel):
    """Configuration for a single MCP server. Spec §4."""

    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    description: str = ""


class SkillsModule(BaseModel):
    """Container for all skills and MCP configs in an Egg."""

    skills: list[SkillRecord] = Field(default_factory=list)
    mcp_configs: dict[str, McpServerConfig] = Field(default_factory=dict)
    """MCP server configs keyed by server name (e.g. ``filesystem``)."""


class MemoryRecord(BaseModel):
    """A single memory record. Spec §5.2."""

    id: str
    text: str
    label: MemoryLabel
    source_framework: str
    source_store: str
    skill_ref: str | None = None
    timestamp: datetime | None = None
    shareable: bool = True
    attachments: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class MemoryModule(BaseModel):
    """Container for all memory records in an Egg."""

    memory: list[MemoryRecord] = Field(default_factory=list)


class SecretRecord(BaseModel):
    """A single secret/PII placeholder record. Spec §6.2."""

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
    """Container for all secret/PII placeholder records in an Egg."""

    secrets: list[SecretRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


class RedactionPolicy(BaseModel):
    """Records what redaction was applied during spawning."""

    pii_redacted: bool = True
    secrets_placeholder_only: bool = True


class SourceEntry(BaseModel):
    """One source that contributed to this egg (multi-source support)."""

    source_type: str
    source_path: str = ""


class Manifest(BaseModel):
    """Top-level Egg metadata. Spec §7."""

    nydus_version: str
    min_nydus_version: str = "0.1.0"
    egg_version: str = "2.0"
    created_at: datetime
    source_type: SourceType
    included_modules: list[str]
    signature: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def source_connector(self) -> str:
        return self.source_type.value if self.source_type else ""

    # Optional
    base_egg: str | None = None
    """Base egg reference this egg inherited from (e.g. 'nydus/openclaw:0.2.0')."""
    redaction_policy: RedactionPolicy | None = None
    build_intent: str | None = None
    tested_targets: list[str] = Field(default_factory=list)
    recommended_targets: list[str] = Field(default_factory=list)
    source_metadata: dict[str, str] = Field(default_factory=dict)

    # CR-002 additions
    sources: list[SourceEntry] = Field(default_factory=list)
    """All source entries when multiple SOURCE directives are used."""


# ---------------------------------------------------------------------------
# Spawn metadata (in-memory only; not part of packed egg JSON)
# ---------------------------------------------------------------------------


class SpawnAttachments(BaseModel):
    """Raw source artifacts and pipeline logs produced during spawn.

    Attached to :class:`Egg` after :meth:`~pynydus.client.Nydus.spawn`; omitted
    when an Egg is loaded from a ``.egg`` archive.
    """

    raw_artifacts: dict[str, str] = Field(default_factory=dict)
    logs: dict[str, list[dict]] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Egg
# ---------------------------------------------------------------------------


class Egg(BaseModel):
    """The canonical portable artifact."""

    manifest: Manifest
    skills: SkillsModule = Field(default_factory=SkillsModule)
    memory: MemoryModule = Field(default_factory=MemoryModule)
    secrets: SecretsModule = Field(default_factory=SecretsModule)
    raw_dir: Path | None = None
    attachments_dir: Path | None = None
    spawn_attachments: SpawnAttachments | None = Field(default=None, exclude=True)

    @property
    def modules(self) -> "ModulesAccessor":
        """Convenience accessor: ``egg.modules.skills``, ``.memory``, ``.secrets``."""
        return ModulesAccessor(self)

    def inspect_secrets(self) -> list[dict]:
        """Return a summary of all secret placeholders and their occurrences."""
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


class ModulesAccessor:
    """Read-only accessor for Egg module record lists (Spec section 19)."""

    __slots__ = ("_egg",)

    def __init__(self, egg: Egg) -> None:
        self._egg = egg

    @property
    def skills(self) -> list[SkillRecord]:
        return self._egg.skills.skills

    @property
    def memory(self) -> list[MemoryRecord]:
        return self._egg.memory.memory

    @property
    def secrets(self) -> list[SecretRecord]:
        return self._egg.secrets.secrets


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
    memory: MemoryModule = Field(default_factory=MemoryModule)
    secrets: SecretsModule = Field(default_factory=SecretsModule)
    raw_artifacts: dict[str, str] = Field(default_factory=dict)
    attachments: dict[str, bytes] = Field(default_factory=dict)
    source_metadata: dict[str, str] = Field(default_factory=dict)

    # Pipeline log — single list of typed events, packed into logs/spawn_log.json
    spawn_log: list[dict] = Field(default_factory=list)


class HatchResult(BaseModel):
    """Output from a hatcher."""

    target: str
    output_dir: Path
    files_created: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    hatch_log: list[dict] = Field(default_factory=list)
    """Structured log entries produced during the hatch pipeline."""


class DiffEntry(BaseModel):
    """A single difference between two Eggs."""

    section: str
    """Which part differs: "manifest", "skills", "memory", "secrets"."""

    change: str
    """Type of change: "added", "removed", "modified"."""

    id: str | None = None
    """Record ID (None for manifest-level changes)."""

    field: str | None = None
    """Which field changed (None for add/remove of whole records)."""

    old: str | None = None
    """Old value (stringified). None for additions."""

    new: str | None = None
    """New value (stringified). None for removals."""


class DiffReport(BaseModel):
    """Result of comparing two Eggs."""

    identical: bool
    entries: list[DiffEntry] = Field(default_factory=list)
