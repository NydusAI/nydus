"""Gitleaks CLI connector for secret detection.

Wraps the external ``gitleaks`` binary to scan directories for secrets (API keys,
tokens, passwords) and build ``SecretRecord`` entries with ``{{SECRET_NNN}}``
placeholders. Descriptions never contain secret substrings.

Requires gitleaks v8+ on ``PATH`` or ``NYDUS_GITLEAKS_PATH``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pynydus.api.schemas import SecretRecord
from pynydus.common.enums import InjectionMode, SecretKind

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Finding:
    """One row from gitleaks JSON report output.

    Attributes:
        file: Absolute path to the file (as reported by gitleaks).
        rule_id: Rule identifier.
        match: Matched substring in the file.
        start_line: 1-based line number.
        start_column: Start column (1-based, gitleaks convention).
        end_column: End column.
        secret: Optional ``Secret`` field from JSON. preferred replacement text
            when it appears verbatim in the file content.
    """

    file: str
    rule_id: str
    match: str
    start_line: int
    start_column: int
    end_column: int
    secret: str = ""


def find_gitleaks() -> str | None:
    """Resolve the ``gitleaks`` executable path.

    Returns:
        Absolute path to the binary, or ``None`` if not found.

    Note:
        ``NYDUS_GITLEAKS_PATH`` is checked first, then ``PATH`` via ``shutil.which``.
    """
    env_path = os.environ.get("NYDUS_GITLEAKS_PATH")
    if env_path and shutil.which(env_path):
        return env_path
    return shutil.which("gitleaks")


def run_gitleaks_scan(root: Path) -> list[Finding]:
    """Run ``gitleaks directory`` on *root* and parse JSON findings.

    Args:
        root: Directory tree to scan (v8.18+ ``gitleaks directory`` mode).

    Returns:
        Parsed ``Finding`` rows. Empty if the report file is empty.

    Raises:
        RuntimeError: If the binary is missing or gitleaks exits with a code
            other than 0 (success) or 1 (leaks found).

    Note:
        Exit code ``1`` means leaks were found, not a failed run. Report JSON
        is written to a temp file because ``-r -`` is unreliable on some
        platforms.
    """
    gl = find_gitleaks()
    if gl is None:
        raise RuntimeError("gitleaks binary not found")

    root = root.resolve()
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tmp:
        report_path = tmp.name

    try:
        cmd = [
            gl,
            "directory",
            str(root),
            "--no-banner",
            "--report-format",
            "json",
            "--report-path",
            report_path,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode not in (0, 1):
            logger.error("gitleaks stderr: %s", result.stderr)
            raise RuntimeError(
                f"gitleaks exited with code {result.returncode}: {result.stderr[:300]}"
            )

        report_text = Path(report_path).read_text(encoding="utf-8").strip()
        if not report_text:
            return []

        raw: list[dict] = json.loads(report_text)
    finally:
        Path(report_path).unlink(missing_ok=True)

    findings: list[Finding] = []
    for entry in raw:
        findings.append(
            Finding(
                file=entry.get("File", ""),
                rule_id=entry.get("RuleID", "unknown"),
                match=entry.get("Match", ""),
                start_line=entry.get("StartLine", 0),
                start_column=entry.get("StartColumn", 0),
                end_column=entry.get("EndColumn", 0),
                secret=entry.get("Secret") or "",
            )
        )
    return findings


def apply_gitleaks_findings(
    files: dict[str, str],
    findings: list[Finding],
    *,
    temp_root: Path,
    start_index: int = 1,
) -> tuple[dict[str, str], list[SecretRecord], int]:
    """Replace gitleaks matches with placeholders and build secret records.

    Args:
        files: Original path-to-content map (keys match the tree under
            *temp_root*).
        findings: Parsed gitleaks rows for that tree.
        temp_root: Temp directory path that was passed to
            :func:`run_gitleaks_scan` (used to map absolute paths back to keys).
        start_index: Starting index for ``{{SECRET_NNN}}`` numbering.

    Returns:
        Tuple of ``(redacted file map, new SecretRecord list, next index)`` after
        the last placeholder.
    """
    resolved_root = temp_root.resolve()
    path_to_key: dict[str, str] = {}
    for key in files:
        path_to_key[str((resolved_root / key).resolve())] = key

    groups: dict[str, list[Finding]] = {}
    for f in findings:
        abs_path = str(Path(f.file).resolve())
        key = path_to_key.get(abs_path)
        if key is None:
            logger.warning("gitleaks finding in unknown file: %s", f.file)
            continue
        groups.setdefault(key, []).append(f)

    redacted = dict(files)
    secrets: list[SecretRecord] = []
    idx = start_index

    for key, group in groups.items():
        content = redacted[key]
        seen_matches: set[str] = set()
        for finding in sorted(group, key=lambda f: (f.start_line, f.start_column)):
            to_replace = (
                finding.secret if finding.secret and finding.secret in content else finding.match
            )
            if not to_replace or to_replace in seen_matches:
                continue
            seen_matches.add(to_replace)

            placeholder = f"{{{{SECRET_{idx:03d}}}}}"
            content = content.replace(to_replace, placeholder, 1)
            secrets.append(
                SecretRecord(
                    id=f"secret_{idx:03d}",
                    placeholder=placeholder,
                    kind=SecretKind.CREDENTIAL,
                    name=finding.rule_id.upper().replace("-", "_"),
                    required_at_hatch=True,
                    injection_mode=InjectionMode.ENV,
                    description=f"gitleaks:{finding.rule_id} in {key}",
                    occurrences=[key],
                )
            )
            idx += 1
        redacted[key] = content

    return redacted, secrets, idx
