"""Unified Nydus configuration — config.json.

All project-level configuration lives in a single file at
``config.json`` in the project root. This includes LLM tier configs,
and will grow to include registry credentials, default settings, etc.

The CLI auto-loads this file. The ``--config`` flag overrides the path.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from pynydus.pkg.llm import NydusLLMConfig

# Default location: ./config.json (project root)
DEFAULT_CONFIG_PATH = Path("config.json")


class RegistryConfig(BaseModel):
    """Nest registry connection settings."""

    url: str
    """Base URL of the Nest server (e.g. ``http://localhost:8000``)."""

    author: str | None = None
    """Default author name attached to pushes."""


class NydusConfig(BaseModel):
    """Top-level Nydus configuration.

    All sections are optional — the config file only needs to contain
    the sections relevant to the operation being performed. If a command
    requires LLM config and it's missing, it will error at that point.
    """

    llm: NydusLLMConfig | None = None
    """LLM tier configuration (simple + complex). Required for refinement."""

    registry: RegistryConfig | None = None
    """Nest registry connection settings. Required for push/pull."""


def load_config(path: Path | None = None) -> NydusConfig:
    """Load Nydus configuration from a JSON file.

    Parameters
    ----------
    path:
        Explicit path to a config file. If ``None``, loads from
        ``./config.json`` in the current directory. If it does not
        exist, returns an empty config (no error).

    Raises
    ------
    FileNotFoundError
        If an explicit path is provided but does not exist.
    ValueError
        If the file exists but contains invalid JSON or schema.
    """
    if path is not None:
        # Explicit path — must exist
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        return _parse_config(path)

    # Default path — missing file is OK (return empty config)
    default = Path.cwd() / DEFAULT_CONFIG_PATH
    if not default.exists():
        return NydusConfig()

    return _parse_config(default)


def _parse_config(path: Path) -> NydusConfig:
    """Parse a config file into NydusConfig."""
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file {path}: {e}") from e

    try:
        return NydusConfig.model_validate(raw)
    except Exception as e:
        raise ValueError(f"Invalid config in {path}: {e}") from e
