"""Nest registry client — push/pull eggs via HTTP.

Communicates with a Nest registry server (FastAPI) to publish and retrieve
eggs. Used by both the SDK (``Nydus.push``/``Nydus.pull``) and the CLI
(``nydus push``/``nydus pull``).

Authentication tokens are stored at ``~/.nydus/credentials.json``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from pynydus.api.errors import RegistryError

logger = logging.getLogger(__name__)

CREDENTIALS_PATH = Path.home() / ".nydus" / "credentials.json"


class NestClient:
    """HTTP client for the Nest egg registry."""

    def __init__(
        self,
        url: str,
        *,
        author: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        """Create a client.

        Args:
            url: Base URL of the Nest server (e.g. ``http://localhost:8000``).
            author: Default author name for pushes when not overridden.
            timeout: Request timeout in seconds.
        """
        # Strip trailing slash for clean URL joining
        self.url = url.rstrip("/")
        self.author = author
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        """Return Authorization header if a stored token exists."""
        token = _load_token(self.url)
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def register(self, username: str, password: str) -> dict[str, Any]:
        """Register a new account on the Nest registry.

        Returns the server's response body on success.
        """
        try:
            response = httpx.post(
                f"{self.url}/auth/register",
                json={"username": username, "password": password},
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise RegistryError(f"Failed to connect to registry at {self.url}: {e}") from e

        if response.status_code == 409:
            raise RegistryError(f"Username '{username}' is already taken")
        if response.status_code not in (200, 201):
            detail = _extract_detail(response)
            raise RegistryError(f"Registration failed (HTTP {response.status_code}): {detail}")

        return response.json()

    def login(self, username: str, password: str) -> str:
        """Authenticate and store the returned JWT token.

        Returns the token string on success.
        """
        try:
            response = httpx.post(
                f"{self.url}/auth/login",
                json={"username": username, "password": password},
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise RegistryError(f"Failed to connect to registry at {self.url}: {e}") from e

        if response.status_code == 401:
            raise RegistryError("Invalid username or password")
        if response.status_code != 200:
            detail = _extract_detail(response)
            raise RegistryError(f"Login failed (HTTP {response.status_code}): {detail}")

        data = response.json()
        token = data.get("token") or data.get("access_token", "")
        if not token:
            raise RegistryError("Server returned no token")

        _save_token(self.url, token)
        logger.info("Logged in to %s as %s", self.url, username)
        return token

    def logout(self) -> bool:
        """Remove the stored token for this registry.

        Returns True if a token was removed, False if none existed.
        """
        removed = _remove_token(self.url)
        if removed:
            logger.info("Logged out from %s", self.url)
        return removed

    # ------------------------------------------------------------------
    # Push / Pull / List
    # ------------------------------------------------------------------

    def push(
        self,
        egg_path: Path,
        *,
        name: str,
        version: str,
        author: str | None = None,
    ) -> dict[str, Any]:
        """Push an egg file to the registry.

        Args:
            egg_path: Path to the ``.egg`` archive on disk.
            name: Registry name (e.g. ``user/my-agent``).
            version: Semver string.
            author: Optional author override for this push.

        Returns:
            Server JSON (name, version, sha256, etc.).

        Raises:
            RegistryError: On HTTP or connection failures, or duplicate version.
        """
        if not egg_path.exists():
            raise RegistryError(f"Egg file not found: {egg_path}")

        effective_author = author or self.author
        params: dict[str, str] = {"name": name, "version": version}
        if effective_author:
            params["author"] = effective_author

        try:
            with open(egg_path, "rb") as f:
                response = httpx.post(
                    f"{self.url}/eggs",
                    params=params,
                    headers=self._auth_headers(),
                    files={"file": (egg_path.name, f, "application/octet-stream")},
                    timeout=self.timeout,
                )
        except httpx.HTTPError as e:
            raise RegistryError(f"Failed to connect to registry at {self.url}: {e}") from e

        if response.status_code == 409:
            raise RegistryError(f"Egg {name}:{version} already exists in registry")
        if response.status_code != 201:
            detail = _extract_detail(response)
            raise RegistryError(f"Push failed (HTTP {response.status_code}): {detail}")

        return response.json()

    def pull(
        self,
        name: str,
        *,
        version: str,
        output_path: Path,
    ) -> Path:
        """Pull an egg from the registry and save to disk.

        Args:
            name: Registry name (e.g. ``user/my-agent``).
            version: Semver string.
            output_path: Destination file path.

        Returns:
            Path written.

        Raises:
            RegistryError: On HTTP errors, 404, SHA mismatch, or connection failure.
        """
        try:
            response = httpx.get(
                f"{self.url}/eggs/{name}/{version}",
                headers=self._auth_headers(),
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise RegistryError(f"Failed to connect to registry at {self.url}: {e}") from e

        if response.status_code == 404:
            raise RegistryError(f"Egg {name}:{version} not found in registry")
        if response.status_code != 200:
            detail = _extract_detail(response)
            raise RegistryError(f"Pull failed (HTTP {response.status_code}): {detail}")

        # Write to disk
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)

        # Verify SHA256 if header present
        sha256_header = response.headers.get("x-egg-sha256")
        if sha256_header:
            import hashlib

            actual = hashlib.sha256(response.content).hexdigest()
            if actual != sha256_header:
                output_path.unlink(missing_ok=True)
                raise RegistryError(f"SHA256 mismatch: expected {sha256_header}, got {actual}")

        return output_path

    def list_versions(self, name: str) -> list[dict[str, Any]]:
        """List all versions of an egg in the registry.

        Args:
            name: Registry-qualified egg name.

        Returns:
            Version metadata dicts from the server.

        Raises:
            RegistryError: On HTTP or connection failures.
        """
        try:
            response = httpx.get(
                f"{self.url}/eggs/{name}/versions",
                headers=self._auth_headers(),
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise RegistryError(f"Failed to connect to registry at {self.url}: {e}") from e

        if response.status_code != 200:
            detail = _extract_detail(response)
            raise RegistryError(f"List versions failed (HTTP {response.status_code}): {detail}")

        data = response.json()
        return data.get("versions", [])


def _extract_detail(response: httpx.Response) -> str:
    """Try to extract a detail message from an error response."""
    try:
        body = response.json()
        return body.get("detail", response.text)
    except Exception:
        return response.text


# ---------------------------------------------------------------------------
# Token storage  (~/.nydus/credentials.json)
# ---------------------------------------------------------------------------


def _load_credentials() -> dict[str, str]:
    """Load the credentials file (registry_url → token mapping)."""
    if not CREDENTIALS_PATH.exists():
        return {}
    try:
        return json.loads(CREDENTIALS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_credentials(data: dict[str, str]) -> None:
    """Persist the credentials file."""
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_token(registry_url: str) -> str | None:
    """Return the stored JWT for a given registry URL, or None."""
    creds = _load_credentials()
    return creds.get(registry_url.rstrip("/"))


def _save_token(registry_url: str, token: str) -> None:
    """Store a JWT for a given registry URL."""
    creds = _load_credentials()
    creds[registry_url.rstrip("/")] = token
    _save_credentials(creds)


def _remove_token(registry_url: str) -> bool:
    """Remove the stored JWT for a given registry URL. Returns True if removed."""
    creds = _load_credentials()
    key = registry_url.rstrip("/")
    if key in creds:
        del creds[key]
        _save_credentials(creds)
        return True
    return False
