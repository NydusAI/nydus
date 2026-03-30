"""Nydus error hierarchy."""


class NydusError(Exception):
    """Base error for all Nydus operations."""


class NydusfileError(NydusError):
    """Error parsing or validating a Nydusfile."""

    def __init__(self, message: str, line: int | None = None):
        self.line = line
        prefix = f"line {line}: " if line is not None else ""
        super().__init__(f"{prefix}{message}")


class ConnectorError(NydusError):
    """Error in a spawner or hatcher connector."""


class EggError(NydusError):
    """Error reading, writing, or packaging an Egg."""


class HatchError(NydusError):
    """Error during the hatching pipeline."""


class ConfigError(NydusError):
    """Error in Nydus configuration."""


class RegistryError(NydusError):
    """Error communicating with the Nest registry."""
