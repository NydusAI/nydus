"""File classification for credential and PII scanning.

Extensions are mapped to categories so the pipeline can skip binary assets and
scan the rest as UTF-8 text. ``partition_files`` only distinguishes **ignored**
from **scannable**. ``structured``, ``markdown``, and ``plain`` labels are for
tests and future use, not separate scan paths today.
"""

from __future__ import annotations

from typing import Literal

FileCategory = Literal["ignored", "structured", "markdown", "plain"]

IGNORED_EXTENSIONS: frozenset[str] = frozenset(
    {
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "ico",
        "svg",
        "pdf",
        "zip",
        "egg",
        "gz",
        "tar",
        "bz2",
        "xz",
        "7z",
        "woff",
        "woff2",
        "ttf",
        "otf",
        "eot",
        "mp3",
        "mp4",
        "wav",
        "ogg",
        "webm",
        "avi",
        "bin",
        "exe",
        "dll",
        "so",
        "dylib",
        "pyc",
        "pyo",
        "class",
    }
)

_STRUCTURED_EXTENSIONS: frozenset[str] = frozenset({"json", "yaml", "yml"})
_MARKDOWN_EXTENSIONS: frozenset[str] = frozenset({"md", "mdx"})


def classify(name: str) -> FileCategory:
    """Classify a filename into a scanning category.

    Args:
        name: File path or basename (extension is inferred from the last ``.``).

    Returns:
        ``"ignored"``, ``"structured"``, ``"markdown"``, or ``"plain"``. Only
        ``"ignored"`` is filtered before scanning in the current pipeline. other
        values are treated as scannable.
    """
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if ext in IGNORED_EXTENSIONS:
        return "ignored"
    if ext in _STRUCTURED_EXTENSIONS:
        return "structured"
    if ext in _MARKDOWN_EXTENSIONS:
        return "markdown"
    return "plain"


def partition_files(
    files: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Split *files* into scannable vs ignored dicts by extension.

    Args:
        files: Map of relative path to file body.

    Returns:
        A pair ``(scannable, ignored)``. Ignored entries are binary or
        non-text assets. scannable entries are scanned for secrets/PII.
    """
    scannable: dict[str, str] = {}
    ignored: dict[str, str] = {}
    for key, content in files.items():
        if classify(key) == "ignored":
            ignored[key] = content
        else:
            scannable[key] = content
    return scannable, ignored
