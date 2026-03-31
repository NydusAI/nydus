"""Multi-vendor LLM client via Instructor. Spec §9.3.

Provides a vendor-agnostic interface for LLM calls with structured
Pydantic output. Each LLM tier (simple/complex) independently specifies
its provider, model, and API key — no defaults, no fallbacks.

Required dependency:
  - instructor >= 1.0
"""

from __future__ import annotations

import os
from typing import TypeVar

import instructor
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

from pynydus.api.errors import ConfigError

# ---------------------------------------------------------------------------
# Configuration models — all fields required, no defaults
# ---------------------------------------------------------------------------


class LLMTierConfig(BaseModel):
    """Configuration for a single LLM tier (simple or complex).

    All fields are mandatory. There are no defaults — the caller must
    explicitly provide provider, model, and api_key.
    """

    provider: str
    """Vendor name: "anthropic", "openai", "mistral", etc."""

    model: str
    """Model identifier: "claude-haiku-4-5-20251001", "gpt-4o", etc."""

    api_key: str
    """API key for this provider."""


class NydusLLMConfig(BaseModel):
    """LLM configuration for the Nydus pipeline.

    Contains two tiers:
    - simple: lightweight model for fast, cheap tasks
    - complex: heavyweight model for nuanced reasoning
    """

    simple: LLMTierConfig
    """Lightweight LLM tier for fast tasks."""

    complex: LLMTierConfig
    """Heavyweight LLM tier for complex reasoning."""


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def _check_allowed_provider(provider: str) -> None:
    """Raise ``ConfigError`` if *provider* is blocked by ``NYDUS_ALLOWED_PROVIDERS``.

    The env var is a comma-separated list of provider names (case-insensitive).
    If the env var is **not set** (or empty), all providers are allowed.
    """
    raw = os.environ.get("NYDUS_ALLOWED_PROVIDERS", "").strip()
    if not raw:
        return  # not set → allow all

    allowed = {p.strip().lower() for p in raw.split(",") if p.strip()}
    if provider.lower() not in allowed:
        raise ConfigError(
            f"Provider '{provider}' is not in NYDUS_ALLOWED_PROVIDERS "
            f"(allowed: {', '.join(sorted(allowed))})"
        )


def create_client(tier: LLMTierConfig) -> instructor.Instructor:
    """Create an Instructor client for the given tier config.

    Uses ``instructor.from_provider`` which supports Anthropic, OpenAI,
    Mistral, Cohere, Google, and many other vendors through a unified
    ``"provider/model"`` string.

    Raises ``ConfigError`` if the provider is blocked by the
    ``NYDUS_ALLOWED_PROVIDERS`` environment variable.
    """
    _check_allowed_provider(tier.provider)
    return instructor.from_provider(
        f"{tier.provider}/{tier.model}",
        api_key=tier.api_key,
    )


_logger = __import__("logging").getLogger(__name__)


def create_completion(
    tier: LLMTierConfig,
    messages: list[dict[str, str]],
    response_model: type[T],
    *,
    max_retries: int = 3,
    log: list[dict] | None = None,
) -> T | None:
    """Run a structured LLM completion and return a validated Pydantic object.

    Returns ``None`` (instead of raising) when the LLM is unavailable,
    allowing the pipeline to fall back to deterministic-only mode.

    Parameters
    ----------
    tier:
        Which LLM tier config to use for this call.
    messages:
        Chat messages in ``[{"role": ..., "content": ...}]`` format.
    response_model:
        A Pydantic BaseModel subclass. Instructor ensures the LLM output
        conforms to this schema (with automatic retries on validation failure).
    max_retries:
        Number of retry attempts if the LLM output fails validation.
    log:
        Optional list to append an ``{"type": "llm_call", ...}`` entry to.
        When provided, timing, provider, and model are captured automatically.

    Returns
    -------
    T | None
        A validated instance of ``response_model``, or ``None`` on failure.
    """
    import time

    try:
        client = create_client(tier)

        start = time.monotonic()
        result = client.chat.completions.create(
            response_model=response_model,
            messages=messages,
            max_retries=max_retries,
        )
        elapsed_ms = round((time.monotonic() - start) * 1000)
    except Exception as exc:
        _logger.warning("LLM unavailable -- falling back to deterministic-only mode: %s", exc)
        return None

    if log is not None:
        entry: dict = {
            "type": "llm_call",
            "provider": tier.provider,
            "model": tier.model,
            "latency_ms": elapsed_ms,
            "response_model": response_model.__name__,
        }
        raw = getattr(result, "_raw_response", None)
        if raw is not None:
            usage = getattr(raw, "usage", None)
            if usage is not None:
                entry["input_tokens"] = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", None)
                entry["output_tokens"] = getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", None)
        log.append(entry)

    return result


