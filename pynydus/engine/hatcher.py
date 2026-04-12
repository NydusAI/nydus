"""Hatching pipeline: transforms an Egg into a target runtime. Spec §13.

Two modes:
  rebuild (default): render from structured egg modules via connector
  passthrough: replay redacted raw/ snapshot verbatim

Pipeline steps:
    1. Version check: verify min_nydus_version compatibility
    2. Build file dict: connector.render() (rebuild) or raw snapshot (passthrough)
    3. LLM polish: adapt/polish on placeholder'd content (no real secrets)
    4. Secrets IN: substitute {{SECRET_NNN}} / {{PII_NNN}} with real values
    5. Write to disk
    6. Hatch log: write hatch_log.json

The LLM never sees real secrets: only placeholder tokens. Real values are
injected as the last transformation before writing to disk.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pynydus.api.errors import ConnectorError, HatchError
from pynydus.api.schemas import Egg, HatchResult
from pynydus.common.enums import AgentType, HatchMode

if TYPE_CHECKING:
    from pynydus.llm import LLMTierConfig

logger = logging.getLogger(__name__)


def hatch(
    egg: Egg,
    *,
    target: AgentType,
    output_dir: Path | None = None,
    secrets_path: Path | None = None,
    mode: HatchMode = HatchMode.REBUILD,
    llm_config: LLMTierConfig | None = None,
    spawn_log: list[dict] | None = None,
    raw_artifacts: dict[str, str] | None = None,
) -> HatchResult:
    """Run the full hatching pipeline (see module docstring for steps).

    Args:
        egg: Egg to hatch (typically from :func:`~pynydus.engine.packager.load`).
        target: Destination runtime (``openclaw``, ``zeroclaw``, ``letta``).
        output_dir: Directory for output files. default ``./agent``.
        secrets_path: ``.env`` file for placeholder substitution (secrets IN).
        mode: ``rebuild`` (structured ``render()``) or ``passthrough`` (raw snapshot).
        llm_config: Optional LLM tier for refinement (spawn and hatch).
        spawn_log: Spawn log entries forwarded to the hatch LLM. defaults to ``egg.spawn_log``.
        raw_artifacts: Redacted ``raw/`` files. defaults to ``egg.raw_artifacts``.
            If the egg was loaded with ``include_raw=False``, ``egg.raw_artifacts`` is
            empty. pass the result of :func:`~pynydus.engine.packager.read_raw_artifacts`
            or reload with ``include_raw=True`` for passthrough.

    Returns:
        ``HatchResult`` with output path, files written, warnings, and hatch log.
    """
    output = output_dir or Path("./agent")
    hatch_log: list[dict] = []
    warnings: list[str] = []

    if spawn_log is None and egg.spawn_log:
        spawn_log = egg.spawn_log
    if raw_artifacts is None and egg.raw_artifacts:
        raw_artifacts = egg.raw_artifacts

    # --- Step 1: Version check ---
    _check_version_compat(egg)

    source_at = egg.manifest.agent_type

    # --- Step 2: Build file dict from modules or raw snapshot ---
    if mode == HatchMode.PASSTHROUGH:
        if source_at != target:
            raise HatchError(
                f"Hatch mode 'passthrough' requires the target to match the egg agent type "
                f"({source_at!r}). Got {target!r}. Use mode 'rebuild' for cross-platform hatching."
            )
        if not raw_artifacts:
            raise HatchError(
                "Hatch mode 'passthrough' requires non-empty raw artifacts from the egg's raw/ "
                "directory. Use load(egg_path) after packing, or pass them from spawn()."
            )
        file_dict = dict(raw_artifacts)
        hatch_log.append(
            {
                "type": "raw_snapshot",
                "source": source_at,
                "target": target,
                "raw_files": len(file_dict),
            }
        )
    else:
        connector = _get_hatcher(target)
        render_result = connector.render(egg)
        file_dict = dict(render_result.files)
        warnings.extend(render_result.warnings)
        hatch_log.append(
            {
                "type": "render_from_modules",
                "phase": "render",
                "source": source_at,
                "target": target,
                "skills": len(egg.skills.skills),
                "memory": len(egg.memory.memory),
                "files": len(file_dict),
            }
        )

    # --- Step 3: LLM polish (on placeholder'd content, no real secrets) ---
    if llm_config is not None and file_dict:
        from pynydus.engine.refinement import refine_hatch

        file_dict = refine_hatch(
            file_dict,
            egg,
            llm_config,
            log=hatch_log,
            spawn_log=spawn_log,
            raw_artifacts=raw_artifacts,
        )

    # --- Step 4: Secrets IN boundary (last transform before disk) ---
    placeholder_map: dict[str, str] = {}
    if secrets_path:
        env_vars = _parse_env_file(secrets_path)
        placeholder_map = _build_placeholder_map(egg, env_vars, secrets_path)
        if placeholder_map:
            file_dict = _substitute_secrets(file_dict, placeholder_map)
            for placeholder in placeholder_map:
                hatch_log.append(
                    {
                        "type": "secret_injection",
                        "placeholder": placeholder,
                    }
                )

    # --- Step 5: Write to disk ---
    files_created = _write_files(file_dict, output)

    result = HatchResult(
        target=target,
        output_dir=output,
        files_created=files_created,
        warnings=warnings,
        hatch_log=hatch_log,
    )

    # --- Step 6: Hatch log ---
    _write_hatch_log(result)

    return result


# ---------------------------------------------------------------------------
# Step 4 helpers: Secret substitution (secrets IN boundary)
# ---------------------------------------------------------------------------


def _substitute_secrets(files: dict[str, str], placeholder_map: dict[str, str]) -> dict[str, str]:
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
# Step 5 helpers: Write files to disk
# ---------------------------------------------------------------------------


def _write_files(files: dict[str, str], output_dir: Path) -> list[str]:
    """Write all file entries to disk. Returns list of created filenames."""
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for fname, content in files.items():
        fpath = output_dir / fname
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
        created.append(fname)
    return created


# ---------------------------------------------------------------------------
# Step 6 helpers: Hatch log
# ---------------------------------------------------------------------------


def _write_hatch_log(result: HatchResult) -> None:
    """Write hatch_log.json to the output directory's logs/ folder."""
    if not result.hatch_log:
        return
    logs_dir = result.output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "hatch_log.json").write_text(
        json.dumps(result.hatch_log, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Hatcher dispatch
# ---------------------------------------------------------------------------


def _get_hatcher(target: AgentType):  # noqa: ANN202
    """Return the hatcher connector for the given agent type."""
    _HATCHERS = {
        AgentType.OPENCLAW: lambda: __import__(
            "pynydus.agents.openclaw.hatcher", fromlist=["OpenClawHatcher"]
        ).OpenClawHatcher(),
        AgentType.LETTA: lambda: __import__(
            "pynydus.agents.letta.hatcher", fromlist=["LettaHatcher"]
        ).LettaHatcher(),
        AgentType.ZEROCLAW: lambda: __import__(
            "pynydus.agents.zeroclaw.hatcher", fromlist=["ZeroClawHatcher"]
        ).ZeroClawHatcher(),
    }
    factory = _HATCHERS.get(target)
    if factory is None:
        raise ConnectorError(f"No hatcher available for: {target}")
    return factory()


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
            f"Missing required secrets in {secrets_path}: {', '.join(missing_required)}"
        )
    return placeholder_map


# ---------------------------------------------------------------------------
# Version check
# ---------------------------------------------------------------------------


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
        current = tuple(int(x) for x in pynydus.__version__.split("."))
        required = tuple(int(x) for x in min_required.split("."))
    except (ValueError, AttributeError):
        return

    if current < required:
        raise HatchError(
            f"This egg requires nydus >= {min_required}, "
            f"but you have {pynydus.__version__}. "
            f"Please upgrade: pip install --upgrade pynydus"
        )
