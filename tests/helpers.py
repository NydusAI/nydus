"""Shared test helpers (importable, unlike conftest.py)."""

from __future__ import annotations

from pathlib import Path

from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective


def config_for(agent_type: str, path: Path, **kwargs) -> NydusfileConfig:
    """Build a minimal NydusfileConfig with a single SOURCE directive."""
    return NydusfileConfig(
        sources=[SourceDirective(agent_type=agent_type, path=str(path))],
        **kwargs,
    )
