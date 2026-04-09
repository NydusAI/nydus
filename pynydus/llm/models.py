"""Pydantic models for LLM configuration."""

from __future__ import annotations

from pydantic import BaseModel


class LLMTierConfig(BaseModel):
    """LLM provider, model, and API key for refinement (spawn and hatch).

    All fields are mandatory. There are no defaults — the caller must
    explicitly provide provider, model, and api_key.
    """

    provider: str
    """Vendor name: "anthropic", "openai", "mistral", etc."""

    model: str
    """Model identifier: "claude-haiku-4-5-20251001", "gpt-4o", etc."""

    api_key: str
    """API key for this provider."""
