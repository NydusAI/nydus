"""Tests for NYDUS_ALLOWED_PROVIDERS environment variable (Priority 2.1)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from pynydus.api.errors import ConfigError
from pynydus.pkg.llm import LLMTierConfig, _check_allowed_provider, create_completion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class DummyResponse(BaseModel):
    answer: str


# ---------------------------------------------------------------------------
# _check_allowed_provider unit tests
# ---------------------------------------------------------------------------


class TestCheckAllowedProvider:
    def test_env_not_set_allows_all(self, monkeypatch: pytest.MonkeyPatch):
        """When NYDUS_ALLOWED_PROVIDERS is not set, any provider is allowed."""
        monkeypatch.delenv("NYDUS_ALLOWED_PROVIDERS", raising=False)
        # Should not raise
        _check_allowed_provider("anthropic")
        _check_allowed_provider("openai")
        _check_allowed_provider("anything")

    def test_env_empty_allows_all(self, monkeypatch: pytest.MonkeyPatch):
        """When NYDUS_ALLOWED_PROVIDERS is empty string, allow all."""
        monkeypatch.setenv("NYDUS_ALLOWED_PROVIDERS", "")
        _check_allowed_provider("anthropic")

    def test_allowed_provider_passes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NYDUS_ALLOWED_PROVIDERS", "anthropic,openai")
        _check_allowed_provider("anthropic")
        _check_allowed_provider("openai")

    def test_blocked_provider_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NYDUS_ALLOWED_PROVIDERS", "anthropic")
        with pytest.raises(ConfigError, match="openai"):
            _check_allowed_provider("openai")

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch):
        """Provider check is case-insensitive."""
        monkeypatch.setenv("NYDUS_ALLOWED_PROVIDERS", "Anthropic,OpenAI")
        _check_allowed_provider("anthropic")
        _check_allowed_provider("OPENAI")
        _check_allowed_provider("Anthropic")

    def test_whitespace_trimmed(self, monkeypatch: pytest.MonkeyPatch):
        """Whitespace around provider names is trimmed."""
        monkeypatch.setenv("NYDUS_ALLOWED_PROVIDERS", " anthropic , openai ")
        _check_allowed_provider("anthropic")
        _check_allowed_provider("openai")

    def test_error_message_includes_allowed_list(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NYDUS_ALLOWED_PROVIDERS", "anthropic,mistral")
        with pytest.raises(ConfigError, match="anthropic"):
            _check_allowed_provider("openai")
        with pytest.raises(ConfigError, match="mistral"):
            _check_allowed_provider("openai")

    def test_single_provider(self, monkeypatch: pytest.MonkeyPatch):
        """Works with a single provider (no comma)."""
        monkeypatch.setenv("NYDUS_ALLOWED_PROVIDERS", "anthropic")
        _check_allowed_provider("anthropic")
        with pytest.raises(ConfigError):
            _check_allowed_provider("openai")


# ---------------------------------------------------------------------------
# Integration: create_completion respects the env var
# ---------------------------------------------------------------------------


class TestCreateCompletionAllowedProviders:
    @patch("pynydus.pkg.llm.create_client")
    def test_allowed_provider_succeeds(
        self, mock_create_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("NYDUS_ALLOWED_PROVIDERS", "anthropic")
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = DummyResponse(answer="ok")
        mock_create_client.return_value = mock_client

        tier = LLMTierConfig(provider="anthropic", model="claude-3", api_key="test")
        result = create_completion(tier, messages=[], response_model=DummyResponse)

        assert result.answer == "ok"

    def test_blocked_provider_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Blocked provider returns None (graceful degradation)."""
        monkeypatch.setenv("NYDUS_ALLOWED_PROVIDERS", "anthropic")
        tier = LLMTierConfig(provider="openai", model="gpt-4o", api_key="test")

        result = create_completion(tier, messages=[], response_model=DummyResponse)
        assert result is None
