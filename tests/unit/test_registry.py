"""Tests for the Nest registry client and wiring (Phase F)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pynydus.api.errors import ConfigError, RegistryError
from pynydus.config import NydusConfig, RegistryConfig, load_config
from pynydus.remote.registry import NestClient

# ---------------------------------------------------------------------------
# RegistryConfig validation
# ---------------------------------------------------------------------------


class TestRegistryConfig:
    def test_requires_url(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RegistryConfig()  # type: ignore[call-arg]

    def test_url_only(self):
        cfg = RegistryConfig(url="http://localhost:8000")
        assert cfg.url == "http://localhost:8000"
        assert cfg.author is None

    def test_url_and_author(self):
        cfg = RegistryConfig(url="http://nest.example.com", author="jae")
        assert cfg.author == "jae"


class TestNydusConfigRegistry:
    def test_empty_config_no_registry(self):
        cfg = NydusConfig()
        assert cfg.registry is None

    def test_config_with_registry(self):
        cfg = NydusConfig(registry=RegistryConfig(url="http://localhost:8000"))
        assert cfg.registry is not None
        assert cfg.registry.url == "http://localhost:8000"

    def test_load_config_with_registry(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NYDUS_REGISTRY_URL", "http://nest.example.com")
        monkeypatch.setenv("NYDUS_REGISTRY_AUTHOR", "jae")
        cfg = load_config()
        assert cfg.registry is not None
        assert cfg.registry.url == "http://nest.example.com"
        assert cfg.registry.author == "jae"

    def test_load_config_registry_only(self, monkeypatch: pytest.MonkeyPatch):
        """Registry URL without LLM env vars."""
        monkeypatch.delenv("NYDUS_LLM_TYPE", raising=False)
        monkeypatch.delenv("NYDUS_LLM_API_KEY", raising=False)
        monkeypatch.setenv("NYDUS_REGISTRY_URL", "http://localhost:8000")
        cfg = load_config()
        assert cfg.registry is not None
        assert cfg.llm is None


# ---------------------------------------------------------------------------
# NestClient — push (mock HTTP)
# ---------------------------------------------------------------------------


class TestNestClientPush:
    @patch("pynydus.remote.registry.httpx.post")
    def test_push_success(self, mock_post: MagicMock, tmp_path: Path):
        egg_file = tmp_path / "agent.egg"
        egg_file.write_bytes(b"egg-data")

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "name": "user/agent",
            "version": "0.1.0",
            "sha256": hashlib.sha256(b"egg-data").hexdigest(),
            "size_bytes": 8,
        }
        mock_post.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        result = client.push(egg_file, name="user/agent", version="0.1.0")

        assert result["name"] == "user/agent"
        assert result["version"] == "0.1.0"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "user/agent" in str(call_kwargs)

    @patch("pynydus.remote.registry.httpx.post")
    def test_push_duplicate_409(self, mock_post: MagicMock, tmp_path: Path):
        egg_file = tmp_path / "agent.egg"
        egg_file.write_bytes(b"data")

        mock_resp = MagicMock()
        mock_resp.status_code = 409
        mock_post.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        with pytest.raises(RegistryError, match="already exists"):
            client.push(egg_file, name="x/y", version="0.1.0")

    def test_push_missing_file(self, tmp_path: Path):
        client = NestClient("http://localhost:8000")
        with pytest.raises(RegistryError, match="not found"):
            client.push(tmp_path / "nope.egg", name="x/y", version="0.1.0")

    @patch("pynydus.remote.registry.httpx.post")
    def test_push_with_author(self, mock_post: MagicMock, tmp_path: Path):
        egg_file = tmp_path / "agent.egg"
        egg_file.write_bytes(b"data")

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"name": "x/y", "version": "0.1.0"}
        mock_post.return_value = mock_resp

        client = NestClient("http://localhost:8000", author="default-author")
        client.push(egg_file, name="x/y", version="0.1.0")

        call_kwargs = mock_post.call_args
        assert "default-author" in str(call_kwargs)

    @patch("pynydus.remote.registry.httpx.post")
    def test_push_connection_error(self, mock_post: MagicMock, tmp_path: Path):
        egg_file = tmp_path / "agent.egg"
        egg_file.write_bytes(b"data")

        mock_post.side_effect = httpx.ConnectError("connection refused")

        client = NestClient("http://localhost:8000")
        with pytest.raises(RegistryError, match="Failed to connect"):
            client.push(egg_file, name="x/y", version="0.1.0")


# ---------------------------------------------------------------------------
# NestClient — pull (mock HTTP)
# ---------------------------------------------------------------------------


class TestNestClientPull:
    @patch("pynydus.remote.registry.httpx.get")
    def test_pull_success(self, mock_get: MagicMock, tmp_path: Path):
        data = b"pulled-egg-data"
        sha = hashlib.sha256(data).hexdigest()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = data
        mock_resp.headers = {"x-egg-sha256": sha}
        mock_get.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        out = tmp_path / "pulled.egg"
        result = client.pull("user/agent", version="0.1.0", output_path=out)

        assert result == out
        assert out.read_bytes() == data

    @patch("pynydus.remote.registry.httpx.get")
    def test_pull_404(self, mock_get: MagicMock, tmp_path: Path):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        with pytest.raises(RegistryError, match="not found"):
            client.pull("x/y", version="9.9.9", output_path=tmp_path / "out.egg")

    @patch("pynydus.remote.registry.httpx.get")
    def test_pull_sha256_mismatch(self, mock_get: MagicMock, tmp_path: Path):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"data"
        mock_resp.headers = {"x-egg-sha256": "bad_hash"}
        mock_get.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        out = tmp_path / "out.egg"
        with pytest.raises(RegistryError, match="SHA256 mismatch"):
            client.pull("x/y", version="0.1.0", output_path=out)
        # File should be cleaned up
        assert not out.exists()

    @patch("pynydus.remote.registry.httpx.get")
    def test_pull_creates_parent_dirs(self, mock_get: MagicMock, tmp_path: Path):
        data = b"data"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = data
        mock_resp.headers = {}
        mock_get.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        out = tmp_path / "nested" / "dir" / "egg.egg"
        client.pull("x/y", version="0.1.0", output_path=out)
        assert out.exists()


# ---------------------------------------------------------------------------
# NestClient — list_versions (mock HTTP)
# ---------------------------------------------------------------------------


class TestNestClientListVersions:
    @patch("pynydus.remote.registry.httpx.get")
    def test_list_versions(self, mock_get: MagicMock):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "name": "user/agent",
            "versions": [
                {"version": "0.2.0", "sha256": "abc"},
                {"version": "0.1.0", "sha256": "def"},
            ],
        }
        mock_get.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        versions = client.list_versions("user/agent")
        assert len(versions) == 2
        assert versions[0]["version"] == "0.2.0"


# ---------------------------------------------------------------------------
# SDK client wiring
# ---------------------------------------------------------------------------


class TestSDKPushPull:
    def test_push_without_registry_config_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """SDK push raises ConfigError when registry not configured."""
        from pynydus.client.client import Nydus

        monkeypatch.delenv("NYDUS_REGISTRY_URL", raising=False)
        nydus = Nydus()
        with pytest.raises(ConfigError, match="Registry not configured"):
            nydus.push(tmp_path / "x.egg", name="x/y", version="0.1.0")

    def test_pull_without_registry_config_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """SDK pull raises ConfigError when registry not configured."""
        from pynydus.client.client import Nydus

        monkeypatch.delenv("NYDUS_REGISTRY_URL", raising=False)
        nydus = Nydus()
        with pytest.raises(ConfigError, match="Registry not configured"):
            nydus.pull("x/y", version="0.1.0")

    @patch("pynydus.remote.registry.httpx.post")
    def test_sdk_push_delegates_to_nest_client(
        self, mock_post: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from pynydus.client.client import Nydus

        egg_file = tmp_path / "agent.egg"
        egg_file.write_bytes(b"data")

        monkeypatch.setenv("NYDUS_REGISTRY_URL", "http://localhost:8000")
        monkeypatch.setenv("NYDUS_REGISTRY_AUTHOR", "jae")

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"name": "x/y", "version": "0.1.0"}
        mock_post.return_value = mock_resp

        nydus = Nydus()
        result = nydus.push(egg_file, name="x/y", version="0.1.0")
        assert result["name"] == "x/y"


# ---------------------------------------------------------------------------
# Spawner registry ref resolution
# ---------------------------------------------------------------------------


class TestRegistryRefResolution:
    def test_is_registry_ref_name_version(self):
        from pynydus.engine.pipeline import _is_registry_ref

        assert _is_registry_ref("user/agent:0.1.0") is True
        assert _is_registry_ref("agent:1.0.0") is True

    def test_is_not_registry_ref_local_egg(self):
        from pynydus.engine.pipeline import _is_registry_ref

        assert _is_registry_ref("./base.egg") is False
        assert _is_registry_ref("/abs/path/base.egg") is False
        assert _is_registry_ref("base.egg") is False

    def test_is_not_registry_ref_relative_path(self):
        from pynydus.engine.pipeline import _is_registry_ref

        assert _is_registry_ref("./some/path") is False
        assert _is_registry_ref("/absolute/path") is False

    def test_is_not_registry_ref_no_colon(self):
        from pynydus.engine.pipeline import _is_registry_ref

        assert _is_registry_ref("openclaw") is False
        assert _is_registry_ref("user/agent") is False


# ---------------------------------------------------------------------------
# Auth: register / login / logout
# ---------------------------------------------------------------------------


class TestNestClientAuth:
    """Test register, login, logout methods and token storage."""

    @patch("pynydus.remote.registry.httpx.post")
    def test_register_success(self, mock_post: MagicMock):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"username": "alice"}
        mock_post.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        result = client.register("alice", "s3cret")
        assert result["username"] == "alice"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "/auth/register" in call_kwargs[0][0]

    @patch("pynydus.remote.registry.httpx.post")
    def test_register_conflict(self, mock_post: MagicMock):
        mock_resp = MagicMock()
        mock_resp.status_code = 409
        mock_post.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        with pytest.raises(RegistryError, match="already taken"):
            client.register("alice", "s3cret")

    @patch("pynydus.remote.registry._save_token")
    @patch("pynydus.remote.registry.httpx.post")
    def test_login_success_stores_token(self, mock_post: MagicMock, mock_save: MagicMock):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"token": "jwt-abc-123"}
        mock_post.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        token = client.login("alice", "s3cret")
        assert token == "jwt-abc-123"
        mock_save.assert_called_once_with("http://localhost:8000", "jwt-abc-123")

    @patch("pynydus.remote.registry.httpx.post")
    def test_login_bad_credentials(self, mock_post: MagicMock):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_post.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        with pytest.raises(RegistryError, match="Invalid username or password"):
            client.login("alice", "wrong")

    @patch("pynydus.remote.registry.httpx.post")
    def test_login_accepts_access_token_key(self, mock_post: MagicMock):
        """Some servers return ``access_token`` instead of ``token``."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "jwt-xyz"}
        mock_post.return_value = mock_resp

        with patch("pynydus.remote.registry._save_token"):
            client = NestClient("http://localhost:8000")
            token = client.login("alice", "s3cret")
            assert token == "jwt-xyz"

    @patch("pynydus.remote.registry._remove_token")
    def test_logout_removes_token(self, mock_remove: MagicMock):
        mock_remove.return_value = True
        client = NestClient("http://localhost:8000")
        assert client.logout() is True
        mock_remove.assert_called_once_with("http://localhost:8000")

    @patch("pynydus.remote.registry._remove_token")
    def test_logout_noop_when_no_token(self, mock_remove: MagicMock):
        mock_remove.return_value = False
        client = NestClient("http://localhost:8000")
        assert client.logout() is False


class TestTokenStorage:
    """Test credential file read/write helpers."""

    def test_roundtrip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from pynydus.remote.registry import (
            _load_token,
            _remove_token,
            _save_token,
        )

        creds_path = tmp_path / ".nydus" / "credentials.json"
        monkeypatch.setattr("pynydus.remote.registry.CREDENTIALS_PATH", creds_path)

        assert _load_token("http://localhost:8000") is None

        _save_token("http://localhost:8000", "tok-1")
        assert _load_token("http://localhost:8000") == "tok-1"

        _save_token("http://other:9000", "tok-2")
        assert _load_token("http://other:9000") == "tok-2"
        assert _load_token("http://localhost:8000") == "tok-1"

        removed = _remove_token("http://localhost:8000")
        assert removed is True
        assert _load_token("http://localhost:8000") is None
        assert _load_token("http://other:9000") == "tok-2"

    def test_remove_nonexistent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from pynydus.remote.registry import _remove_token

        creds_path = tmp_path / ".nydus" / "credentials.json"
        monkeypatch.setattr("pynydus.remote.registry.CREDENTIALS_PATH", creds_path)

        assert _remove_token("http://unknown:8000") is False


class TestAuthHeaders:
    """Test that auth token is sent with push/pull/list requests."""

    @patch("pynydus.remote.registry._load_token", return_value="tok-abc")
    @patch("pynydus.remote.registry.httpx.get")
    def test_pull_sends_auth_header(
        self, mock_get: MagicMock, mock_load: MagicMock, tmp_path: Path
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"egg-data"
        mock_resp.headers = {}
        mock_get.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        client.pull("x/y", version="1.0", output_path=tmp_path / "out.egg")

        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs.get("headers", {}).get("Authorization") == "Bearer tok-abc"

    @patch("pynydus.remote.registry._load_token", return_value=None)
    @patch("pynydus.remote.registry.httpx.get")
    def test_pull_no_auth_when_not_logged_in(
        self, mock_get: MagicMock, mock_load: MagicMock, tmp_path: Path
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"egg-data"
        mock_resp.headers = {}
        mock_get.return_value = mock_resp

        client = NestClient("http://localhost:8000")
        client.pull("x/y", version="1.0", output_path=tmp_path / "out.egg")

        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs.get("headers", {}) == {}
