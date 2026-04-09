"""Centralised ``StrEnum`` definitions for the Nydus project.

String-valued identifiers used across production code and tests are defined here
so imports resolve to a single source of truth.
"""

from __future__ import annotations

from enum import StrEnum

# ---------------------------------------------------------------------------
# Source / platform
# ---------------------------------------------------------------------------


class AgentType(StrEnum):
    """Supported agent platforms."""

    OPENCLAW = "openclaw"
    ZEROCLAW = "zeroclaw"
    LETTA = "letta"


# ---------------------------------------------------------------------------
# Egg structure
# ---------------------------------------------------------------------------


class Bucket(StrEnum):
    """Top-level module buckets in an Egg."""

    SKILL = "skill"
    MEMORY = "memory"
    SECRET = "secret"


class SecretKind(StrEnum):
    """Kind of redacted value: credential (gitleaks) or PII (Presidio)."""

    CREDENTIAL = "credential"
    PII = "pii"


class InjectionMode(StrEnum):
    """How a secret value is provided at hatch time."""

    ENV = "env"
    SUBSTITUTION = "substitution"


class MemoryLabel(StrEnum):
    """Canonical labels for memory records, assigned by spawners."""

    PERSONA = "persona"
    FLOW = "flow"
    CONTEXT = "context"
    STATE = "state"


# ---------------------------------------------------------------------------
# Hatching
# ---------------------------------------------------------------------------


class HatchMode(StrEnum):
    """Hatching mode: rebuild from structured modules or passthrough raw snapshot."""

    REBUILD = "rebuild"
    PASSTHROUGH = "passthrough"


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


class DiffChange(StrEnum):
    """Type of change reported in a diff entry."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


# ---------------------------------------------------------------------------
# Nydusfile DSL
# ---------------------------------------------------------------------------


class Directive(StrEnum):
    """All recognised Nydusfile directives."""

    FROM = "FROM"
    SOURCE = "SOURCE"
    REDACT = "REDACT"
    EXCLUDE = "EXCLUDE"
    LABEL = "LABEL"
    ADD = "ADD"
    SET = "SET"
    REMOVE = "REMOVE"

    @property
    def is_singular(self) -> bool:
        """Whether this directive takes a single argument (``FROM`` or ``REDACT``).

        Returns:
            ``True`` if this member is ``FROM`` or ``REDACT``.
        """
        return self in {Directive.FROM, Directive.REDACT}

    @property
    def is_merge(self) -> bool:
        """Whether this directive is a merge operation (``ADD``, ``SET``, ``REMOVE``).

        Returns:
            ``True`` if this member is ``ADD``, ``SET``, or ``REMOVE``.
        """
        return self in {Directive.ADD, Directive.SET, Directive.REMOVE}
