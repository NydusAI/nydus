"""PyNydus: portable state transport for AI agents.

Re-exports the public Egg model, the ``Nydus`` client, and common types for
library consumers.

Attributes:
    __version__: Package version string.
    EGG_SPEC_VERSION: Supported on-disk Egg format version.
"""

from __future__ import annotations

from pynydus.api.schemas import (
    AgentSkill,
    DiffReport,
    Egg,
    HatchResult,
    Manifest,
    McpModule,
    MemoryRecord,
    SecretRecord,
    ValidationReport,
)
from pynydus.client.client import Nydus
from pynydus.common.enums import HatchMode

__version__ = "0.0.7"
EGG_SPEC_VERSION = "1.0"

__all__ = [
    "AgentSkill",
    "DiffReport",
    "EGG_SPEC_VERSION",
    "Egg",
    "HatchMode",
    "HatchResult",
    "Manifest",
    "McpModule",
    "MemoryRecord",
    "Nydus",
    "SecretRecord",
    "ValidationReport",
]
