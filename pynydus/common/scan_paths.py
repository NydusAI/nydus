"""File classification for credential and PII scanning.

``classify`` returns **ignored** for known binary/non-text extensions and
**plain** for everything else. ``partition_files`` splits on that: ignored
entries are skipped. The rest are scanned as UTF-8 text.
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


def classify(name: str) -> FileCategory:
    """Classify a filename into a scanning category.

    Args:
        name: File path or basename (extension is inferred from the last ``.``).

    Returns:
        ``"ignored"`` for binary/non-text assets, ``"plain"`` for everything
        else. Only ``"ignored"`` is filtered before scanning.
    """
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return "ignored" if ext in IGNORED_EXTENSIONS else "plain"


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
