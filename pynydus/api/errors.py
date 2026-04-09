"""Nydus exception hierarchy.

All user-visible failures from PyNydus inherit from ``NydusError``.
"""


class NydusError(Exception):
    """Base class for Nydus failures."""


class NydusfileError(NydusError):
    """Raised when a Nydusfile cannot be parsed or validated."""

    def __init__(self, message: str, line: int | None = None):
        """Build a Nydusfile error, optionally tied to a line number.

        Args:
            message: Human-readable explanation.
            line: Source line in the Nydusfile, if known.
        """
        self.line = line
        prefix = f"line {line}: " if line is not None else ""
        super().__init__(f"{prefix}{message}")


class ConnectorError(NydusError):
    """Raised when a spawner or hatcher connector fails."""


class EggError(NydusError):
    """Raised when an Egg cannot be read, written, or packaged."""


class HatchError(NydusError):
    """Raised when the hatching pipeline fails."""


class ConfigError(NydusError):
    """Raised when Nydus configuration is invalid or missing."""


class GitleaksNotFoundError(NydusError):
    """Raised when secret scanning is required but gitleaks is not available.

    Spawn with ``REDACT true`` and ``SOURCE`` needs the ``gitleaks`` CLI.
    Install from https://github.com/gitleaks/gitleaks or set
    ``NYDUS_GITLEAKS_PATH`` to the binary path.
    """


class RegistryError(NydusError):
    """Raised when the Nest registry request fails."""
