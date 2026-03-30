"""Hatching pipeline — transforms an Egg into a target runtime. Spec §13.

Symmetric boundaries — secrets cross at the file level:

1. Version check  — Verify min_nydus_version
2. Pass-through   — Check if source == target (same-platform shortcut)
3. Render         — hatcher.render(egg) -> file dict with placeholders
4. Secrets IN     — Substitute {{SECRET_NNN}} / {{PII_NNN}} with real values
5. LLM polish     — Adapt/polish file contents for target platform
6. Write to disk  — Write all files from dict to output_dir
7. Hatch log      — Write hatch_log.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pynydus.api.errors import ConnectorError, HatchError
from pynydus.api.schemas import Egg, HatchResult, SourceType

if TYPE_CHECKING:
    from pynydus.pkg.llm import NydusLLMConfig

logger = logging.getLogger(__name__)


def hatch(
    egg: Egg,
    *,
    target: str,
    output_dir: Path | None = None,
    secrets_path: Path | None = None,
    reconstruct: bool = False,
    llm_config: NydusLLMConfig | None = None,
    spawn_log: list[dict] | None = None,
    raw_artifacts: dict[str, str] | None = None,
) -> HatchResult:
    """Run the full 7-phase hatching pipeline.

    Parameters
    ----------
    egg:
        The Egg to hatch (unpacked from a ``.egg`` archive).
    target:
        Target runtime: ``"openclaw"``, ``"zeroclaw"``, or ``"letta"``.
    output_dir:
        Directory to write target-native files. Defaults to ``./agent``.
    secrets_path:
        Path to a ``.env`` file for placeholder resolution (secrets IN).
    reconstruct:
        Force full reconstruction even when source and target match.
    llm_config:
        Two-tier LLM configuration for target-specific refinement.
    spawn_log:
        Spawn pipeline log entries, forwarded to the hatch LLM.
    raw_artifacts:
        Redacted source files from the egg archive's ``raw/`` directory.
        Used for pass-through mode.

    Returns
    -------
    HatchResult
        Output directory, list of created files, warnings, and hatch log.
    """
    output = output_dir or Path("./agent")
    hatch_log: list[dict] = []
    warnings: list[str] = []

    # --- Phase 1: Version check ---
    _check_version_compat(egg)

    # --- Phase 2: Pass-through check ---
    is_same_platform = str(egg.manifest.source_type) == target
    pass_through = is_same_platform and not reconstruct
    if pass_through:
        logger.info("Source and target are both %s — pass-through mode", target)

    # --- Phase 3: Render (produces "raw" output with placeholders) ---
    if pass_through and raw_artifacts:
        file_dict = dict(raw_artifacts)
        hatch_log.append({
            "type": "pass_through",
            "source": str(egg.manifest.source_type),
            "target": target,
            "raw_files": len(file_dict),
        })
    else:
        connector = _get_hatcher(target)
        render_result = connector.render(egg)
        file_dict = dict(render_result.files)
        warnings.extend(render_result.warnings)

        if pass_through:
            hatch_log.append({
                "type": "pass_through",
                "source": str(egg.manifest.source_type),
                "target": target,
            })
        else:
            hatch_log.append({
                "type": "transform",
                "phase": "render",
                "target": target,
                "skills": len(egg.skills.skills),
                "memory": len(egg.memory.memory),
                "files": len(file_dict),
            })

    # --- Phase 4: Secrets IN boundary (raw -> target files) ---
    placeholder_map: dict[str, str] = {}
    if secrets_path:
        env_vars = _parse_env_file(secrets_path)
        placeholder_map = _build_placeholder_map(egg, env_vars, secrets_path)
        if placeholder_map:
            file_dict = _substitute_secrets(file_dict, placeholder_map)
            for placeholder in placeholder_map:
                hatch_log.append({
                    "type": "secret_injection",
                    "placeholder": placeholder,
                })

    # --- Phase 5: LLM polish ---
    if llm_config is not None and file_dict:
        from pynydus.engine.refinement import refine_hatch

        file_dict = refine_hatch(
            file_dict, egg, llm_config,
            log=hatch_log, spawn_log=spawn_log,
            raw_artifacts=raw_artifacts,
        )

    # --- Phase 6: Write to disk ---
    files_created = _write_files(file_dict, output)

    result = HatchResult(
        target=target,
        output_dir=output,
        files_created=files_created,
        warnings=warnings,
        hatch_log=hatch_log,
    )

    # --- Phase 7: Hatch log ---
    _write_hatch_log(result)

    return result


# ---------------------------------------------------------------------------
# Phase 4: Secret substitution
# ---------------------------------------------------------------------------


def _substitute_secrets(
    files: dict[str, str], placeholder_map: dict[str, str]
) -> dict[str, str]:
    """Replace all {{SECRET_NNN}} / {{PII_NNN}} placeholders with real values."""
    result: dict[str, str] = {}
    for fname, content in files.items():
        new_content = content
        for placeholder, value in placeholder_map.items():
            if placeholder in new_content:
                new_content = new_content.replace(placeholder, value)
        result[fname] = new_content
    return result


# ---------------------------------------------------------------------------
# Phase 6: Write files to disk
# ---------------------------------------------------------------------------


def _write_files(files: dict[str, str], output_dir: Path) -> list[str]:
    """Write all file entries to disk. Returns list of created filenames."""
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for fname, content in files.items():
        fpath = output_dir / fname
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content)
        created.append(fname)
    return created


# ---------------------------------------------------------------------------
# Hatch log
# ---------------------------------------------------------------------------


def _write_hatch_log(result: HatchResult) -> None:
    """Write hatch_log.json to the output directory's logs/ folder."""
    if not result.hatch_log:
        return
    logs_dir = result.output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "hatch_log.json").write_text(
        json.dumps(result.hatch_log, indent=2)
    )


# ---------------------------------------------------------------------------
# Hatcher dispatch
# ---------------------------------------------------------------------------


def _get_hatcher(target: str):  # noqa: ANN202
    """Return the hatcher connector for the given target."""
    if target == SourceType.OPENCLAW:
        from pynydus.agents.openclaw.hatcher import OpenClawHatcher

        return OpenClawHatcher()

    if target == SourceType.LETTA:
        from pynydus.agents.letta.hatcher import LettaHatcher

        return LettaHatcher()

    if target == SourceType.ZEROCLAW:
        from pynydus.agents.zeroclaw.hatcher import ZeroClawHatcher

        return ZeroClawHatcher()

    raise ConnectorError(f"No hatcher available for target: {target}")


# ---------------------------------------------------------------------------
# Secrets helpers
# ---------------------------------------------------------------------------


def _parse_env_file(secrets_path: Path) -> dict[str, str]:
    """Parse a .env file into a dict of key=value pairs."""
    if not secrets_path.exists():
        raise HatchError(f"Secrets file not found: {secrets_path}")

    env_vars: dict[str, str] = {}
    for line in secrets_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        env_vars[key.strip()] = value.strip()
    return env_vars


def _build_placeholder_map(
    egg: Egg, env_vars: dict[str, str], secrets_path: Path
) -> dict[str, str]:
    """Build placeholder -> value mapping, raising if required secrets are missing."""
    placeholder_map: dict[str, str] = {}
    missing_required: list[str] = []

    for secret in egg.secrets.secrets:
        if secret.name in env_vars:
            placeholder_map[secret.placeholder] = env_vars[secret.name]
        elif secret.required_at_hatch:
            missing_required.append(secret.name)

    if missing_required:
        raise HatchError(
            f"Missing required secrets in {secrets_path}: "
            f"{', '.join(missing_required)}"
        )
    return placeholder_map


# ---------------------------------------------------------------------------
# Version check
# ---------------------------------------------------------------------------


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a semver string into a comparable tuple of ints."""
    return tuple(int(x) for x in v.split("."))


def _check_version_compat(egg: Egg) -> None:
    """Reject eggs that require a newer Nydus version than we have."""
    import pynydus

    logger.debug(
        "Egg spec version: %s (runtime: %s)",
        egg.manifest.egg_version,
        pynydus.EGG_SPEC_VERSION,
    )

    min_required = getattr(egg.manifest, "min_nydus_version", None)
    if not min_required:
        return

    try:
        current = _parse_version(pynydus.__version__)
        required = _parse_version(min_required)
    except (ValueError, AttributeError):
        return

    if current < required:
        raise HatchError(
            f"This egg requires nydus >= {min_required}, "
            f"but you have {pynydus.__version__}. "
            f"Please upgrade: pip install --upgrade pynydus"
        )
