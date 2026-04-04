"""Instructor-based LLM client factory and completions. Spec §9.3.

Provides a vendor-agnostic interface for LLM calls with structured
Pydantic output. Each ``LLMTierConfig`` specifies its provider, model, and
API key — no defaults, no fallbacks.

Required dependency:
  - instructor >= 1.0
"""

from __future__ import annotations

from typing import TypeVar

import instructor
from pydantic import BaseModel

from pynydus.llm.models import LLMTierConfig

T = TypeVar("T", bound=BaseModel)


def create_client(tier: LLMTierConfig) -> instructor.Instructor:
    """Create an Instructor client for the given tier config.

    Uses ``instructor.from_provider`` which supports Anthropic, OpenAI,
    Mistral, Cohere, Google, and other vendors via a ``"provider/model"`` string.

    Args:
        tier: Provider, model, and API key (all required).

    Returns:
        Configured Instructor client.
    """
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
    """Run a structured LLM completion and return a validated Pydantic model.

    Returns ``None`` (instead of raising) when the LLM is unavailable so the
    pipeline can fall back to deterministic-only mode.

    Args:
        tier: LLM tier config to use for this call.
        messages: Chat messages as ``[{"role": ..., "content": ...}, ...]``.
        response_model: Pydantic ``BaseModel`` subclass; Instructor validates
            output against this schema (with retries on validation failure).
        max_retries: Max retries when validation fails.
        log: If set, appends an ``{"type": "llm_call", ...}`` entry with
            timing, provider, model, and optional token usage.

    Returns:
        A validated instance of *response_model*, or ``None`` on failure.
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
                entry["input_tokens"] = getattr(usage, "input_tokens", None) or getattr(
                    usage, "prompt_tokens", None
                )
                entry["output_tokens"] = getattr(usage, "output_tokens", None) or getattr(
                    usage, "completion_tokens", None
                )
        log.append(entry)

    return result
