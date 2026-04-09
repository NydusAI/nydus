"""Multi-vendor LLM client via Instructor. Spec §9.3.

Re-exports configuration models and client helpers from submodules.
"""

from __future__ import annotations

from pynydus.llm.client import create_client, create_completion
from pynydus.llm.models import LLMTierConfig

__all__ = [
    "LLMTierConfig",
    "create_client",
    "create_completion",
]
