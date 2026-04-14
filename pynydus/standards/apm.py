"""APM standard: extract only.

Pure passthrough — Nydus does not parse, validate, or generate ``apm.yml``.
"""

from __future__ import annotations

from pynydus.api.schemas import Egg


def extract(egg: Egg) -> dict[str, str]:
    """Extract the passthrough ``apm.yml`` from the egg.

    Returns:
        ``{"apm.yml": <content>}`` or empty dict if absent.
    """
    if egg.apm_yml is None:
        return {}

    return {"apm.yml": egg.apm_yml}
