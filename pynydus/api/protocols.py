"""Abstract base classes for agent connectors (spawners and hatchers)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pynydus.api.raw_types import ParseResult, RenderResult
    from pynydus.api.schemas import Egg


class Spawner(ABC):
    """Base class for all platform spawners.

    A spawner reads redacted source files and produces a ``ParseResult``
    containing structured skills, memory, MCP configs, and neutral metadata.
    """

    @abstractmethod
    def parse(self, files: dict[str, str]) -> ParseResult:
        """Parse redacted source files into structured records.

        Args:
            files: Mapping of relative path to UTF-8 content (already redacted).

        Returns:
            Structured parse output.
        """
        ...


class Hatcher(ABC):
    """Base class for all platform hatchers.

    A hatcher takes a loaded Egg and produces target-platform files
    in an output directory.
    """

    @abstractmethod
    def render(self, egg: Egg, output_dir: Path) -> RenderResult:
        """Render egg contents into target-platform files.

        Args:
            egg: Loaded Egg with all modules.
            output_dir: Target output directory (connectors may ignore until write).

        Returns:
            File mapping and optional warnings (placeholders intact).
        """
        ...
