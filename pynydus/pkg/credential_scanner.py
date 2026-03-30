"""Generic credential detection and redaction.

Scans file contents for credential-like values (API keys, tokens, passwords)
and replaces them with ``{{SECRET_NNN}}`` placeholders.  Returns the redacted
file contents alongside ``SecretRecord`` objects for the secrets module.

This module consolidates credential-detection logic previously duplicated
across all three spawner connectors (OpenClaw, ZeroClaw, Letta).
"""

from __future__ import annotations

import json

from pynydus.api.schemas import InjectionMode, SecretKind, SecretRecord
from pynydus.pkg.connector_utils import (
    SECRET_PATTERN as _SECRET_PATTERN,
    extract_key_name as _extract_key_name,
    looks_like_placeholder as _looks_like_placeholder,
)

_CREDENTIAL_KEYWORDS = ("key", "secret", "token", "password", "credential", "auth")

_SKIP_VALUES = frozenset({"", "none", "null", "true", "false"})


class _Counter:
    """Mutable counter shared across recursive calls."""

    __slots__ = ("value",)

    def __init__(self, start: int) -> None:
        self.value = start

    def next(self) -> int:
        v = self.value
        self.value += 1
        return v


def scan_credentials(
    files: dict[str, str],
    *,
    start_index: int = 1,
) -> tuple[dict[str, str], list[SecretRecord]]:
    """Scan file contents for credential-like values, replace with placeholders.

    Parameters
    ----------
    files:
        Mapping of ``filename -> UTF-8 content``.
    start_index:
        Starting counter for ``{{SECRET_NNN}}`` placeholders.

    Returns
    -------
    tuple[dict[str, str], list[SecretRecord]]
        ``(redacted_files, secrets)`` where redacted_files has credential
        values replaced with ``{{SECRET_NNN}}`` placeholders.
    """
    counter = _Counter(start_index)
    secrets: list[SecretRecord] = []
    redacted: dict[str, str] = {}

    for fname, content in files.items():
        new_content, found = _scan_file(fname, content, counter)
        redacted[fname] = new_content
        secrets.extend(found)

    return redacted, secrets


def _scan_file(
    fname: str, content: str, counter: _Counter
) -> tuple[str, list[SecretRecord]]:
    """Scan a single file for credentials and replace values inline."""
    if fname.endswith(".json"):
        return _scan_json(fname, content, counter)
    if fname.endswith((".yaml", ".yml")):
        return _scan_yaml(fname, content, counter)
    return content, []


def _scan_json(
    fname: str, content: str, counter: _Counter
) -> tuple[str, list[SecretRecord]]:
    """Scan a JSON file for credential-like key/value pairs."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content, []

    if not isinstance(data, dict):
        return content, []

    replacements: list[tuple[str, str]] = []  # (original_value, placeholder)
    secrets: list[SecretRecord] = []

    _walk_dict(data, fname, replacements, secrets, counter)

    new_content = content
    for original_value, placeholder in replacements:
        new_content = new_content.replace(
            json.dumps(original_value), json.dumps(placeholder), 1
        )

    return new_content, secrets


def _walk_dict(
    data: dict,
    source_file: str,
    replacements: list[tuple[str, str]],
    secrets: list[SecretRecord],
    counter: _Counter,
    prefix: str = "",
) -> None:
    """Recursively walk a dict looking for credential-like values."""
    for key, val in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            _walk_dict(val, source_file, replacements, secrets, counter, full_key)
            continue
        if not isinstance(val, str):
            continue
        if val.lower() in _SKIP_VALUES:
            continue
        if _looks_like_placeholder(val):
            continue
        if not any(kw in key.lower() for kw in _CREDENTIAL_KEYWORDS):
            continue

        idx = counter.next()
        placeholder = f"{{{{SECRET_{idx:03d}}}}}"
        name = key.upper().replace("-", "_")

        replacements.append((val, placeholder))
        secrets.append(
            SecretRecord(
                id=f"secret_{idx:03d}",
                placeholder=placeholder,
                kind=SecretKind.CREDENTIAL,
                name=name,
                required_at_hatch=True,
                injection_mode=InjectionMode.ENV,
                description=f"value_hint={val[:8]}..." if len(val) > 8 else f"value_hint={val}",
                occurrences=[source_file],
            )
        )


def _scan_yaml(
    fname: str, content: str, counter: _Counter
) -> tuple[str, list[SecretRecord]]:
    """Scan a YAML file for credential-like key/value pairs using regex."""
    secrets: list[SecretRecord] = []
    new_content = content

    for match in _SECRET_PATTERN.finditer(content):
        val = match.group(1)
        if _looks_like_placeholder(val):
            continue
        if val.lower() in _SKIP_VALUES:
            continue

        idx = counter.next()
        placeholder = f"{{{{SECRET_{idx:03d}}}}}"
        key_name = _extract_key_name(match.group(0))
        name = key_name.upper().replace("-", "_")

        new_content = new_content.replace(val, placeholder, 1)
        secrets.append(
            SecretRecord(
                id=f"secret_{idx:03d}",
                placeholder=placeholder,
                kind=SecretKind.CREDENTIAL,
                name=name,
                required_at_hatch=True,
                injection_mode=InjectionMode.ENV,
                description=f"value_hint={val[:8]}..." if len(val) > 8 else f"value_hint={val}",
                occurrences=[fname],
            )
        )

    return new_content, secrets
