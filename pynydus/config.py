"""Nydus configuration from environment variables only.

LLM (refinement / LLM tiers):

- ``NYDUS_LLM_TYPE`` — ``provider/model`` (e.g. ``anthropic/claude-3-5-haiku-20241022``)
- ``NYDUS_LLM_API_KEY`` — API key for that tier

Both must be set together to enable ``NydusConfig.llm``. If only one is set,
:func:`load_config` raises ``ValueError``.

Nest registry (``push`` / ``pull`` / ``FROM nydus/...``):

- ``NYDUS_REGISTRY_URL`` — base URL of the Nest server (e.g. ``http://localhost:8000``)
- ``NYDUS_REGISTRY_AUTHOR`` — optional default author for pushes
"""

from __future__ import annotations

import os

from pydantic import BaseModel

from pynydus.llm.models import LLMTierConfig


class RegistryConfig(BaseModel):
    """Nest registry connection settings."""

    url: str
    """Base URL of the Nest server (e.g. ``http://localhost:8000``)."""

    author: str | None = None
    """Default author name attached to pushes."""


class NydusConfig(BaseModel):
    """Top-level Nydus configuration loaded from the environment."""

    llm: LLMTierConfig | None = None
    """LLM provider, model, and API key. Required for refinement when set."""

    registry: RegistryConfig | None = None
    """Nest registry connection settings. Required for push/pull when set."""


def load_config() -> NydusConfig:
    """Load ``NydusConfig`` from ``NYDUS_*`` environment variables.

    Returns:
        Validated configuration. Missing LLM or registry env vars yield ``None``
        for those sections (no error).

    Raises:
        ValueError: If ``NYDUS_LLM_TYPE`` and ``NYDUS_LLM_API_KEY`` are partially set,
            or if ``NYDUS_LLM_TYPE`` is malformed.
    """
    llm = _llm_from_env()
    registry = _registry_from_env()
    return NydusConfig(llm=llm, registry=registry)


def _llm_from_env() -> LLMTierConfig | None:
    type_str = os.environ.get("NYDUS_LLM_TYPE", "").strip()
    api_key = os.environ.get("NYDUS_LLM_API_KEY")
    has_type = bool(type_str)
    has_key = api_key is not None and str(api_key).strip() != ""

    if not has_type and not has_key:
        return None
    if has_type != has_key:
        raise ValueError(
            "NYDUS_LLM_TYPE and NYDUS_LLM_API_KEY must both be set (or both unset) "
            "to configure the LLM tier."
        )

    if "/" not in type_str:
        raise ValueError(
            "NYDUS_LLM_TYPE must be 'provider/model' (e.g. anthropic/claude-3-5-haiku-20241022)"
        )
    provider, _, rest = type_str.partition("/")
    if not provider.strip() or not rest.strip():
        raise ValueError("NYDUS_LLM_TYPE must be 'provider/model'")
    return LLMTierConfig(
        provider=provider.strip(),
        model=rest.strip(),
        api_key=str(api_key).strip(),
    )


def _registry_from_env() -> RegistryConfig | None:
    url = os.environ.get("NYDUS_REGISTRY_URL", "").strip()
    if not url:
        return None
    author_raw = os.environ.get("NYDUS_REGISTRY_AUTHOR", "").strip()
    author = author_raw if author_raw else None
    return RegistryConfig(url=url, author=author)
