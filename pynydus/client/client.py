"""Python SDK: mirrors the CLI 1:1. Spec §19.

Usage::

    from pynydus import Nydus

    ny = Nydus()
    egg = ny.spawn()  # reads ./Nydusfile
    egg = ny.spawn(nydusfile="path/to/Nydusfile")
    path = ny.save(egg, Path("agent.egg"))

    egg = ny.load(Path("agent.egg"))
    egg.skills.skills  # list of AgentSkill
    egg.memory.memory  # list of MemoryRecord
    egg.inspect_secrets()

    result = ny.hatch(egg, target=AgentType.LETTA)
"""

from __future__ import annotations

from pathlib import Path

from pynydus.api.schemas import (
    DiffReport,
    Egg,
    HatchResult,
    ValidationReport,
)
from pynydus.common.enums import AgentType, HatchMode
from pynydus.config import NydusConfig, load_config


class Nydus:
    """Main SDK entry point (mirrors CLI behavior)."""

    def __init__(self) -> None:
        """Load LLM and registry settings from environment variables.

        Set ``NYDUS_LLM_TYPE`` and ``NYDUS_LLM_API_KEY`` for refinement.
        Set ``NYDUS_REGISTRY_URL`` (and optionally ``NYDUS_REGISTRY_AUTHOR``) for
        registry operations. See :mod:`pynydus.config`.
        """
        self._config: NydusConfig = load_config()

    def spawn(
        self,
        nydusfile: Path | str | None = None,
    ) -> Egg:
        """Spawn an Egg from a Nydusfile.

        Args:
            nydusfile: Path to a Nydusfile. If ``None``, resolves one in
                the current working directory.

        Returns:
            ``Egg`` with ``raw_artifacts`` and ``spawn_log`` populated from the
            pipeline. Use :meth:`save` to write a ``.egg`` file.
        """
        from pynydus.engine.nydusfile import parse_file, resolve_nydusfile
        from pynydus.engine.pipeline import spawn as engine_spawn

        if nydusfile:
            nydusfile_path = Path(nydusfile).resolve()
        else:
            nydusfile_path = resolve_nydusfile(Path.cwd())

        nydusfile_dir = nydusfile_path.parent
        config = parse_file(str(nydusfile_path))
        egg, raw_artifacts, logs = engine_spawn(
            config,
            nydusfile_dir=nydusfile_dir,
            llm_config=self._config.llm,
        )

        spawn_log_list = logs.get("spawn_log", [])
        return egg.model_copy(
            update={
                "raw_artifacts": raw_artifacts,
                "spawn_log": spawn_log_list,
            }
        )

    def hatch(
        self,
        egg: Egg,
        *,
        target: AgentType,
        output_dir: Path | None = None,
        secrets: str | Path | None = None,
        mode: HatchMode = HatchMode.REBUILD,
        spawn_log: list[dict] | None = None,
        raw_artifacts: dict[str, str] | None = None,
    ) -> HatchResult:
        """Hatch an Egg into a target runtime.

        Args:
            egg: Loaded Egg to render.
            target: Destination platform.
            output_dir: Directory for output files (connector default if omitted).
            secrets: Path to ``.env`` for placeholder substitution.
            mode: ``rebuild`` (structured modules) or ``passthrough`` (raw snapshot).
            spawn_log: Spawn pipeline log for the hatch LLM. defaults to ``egg.spawn_log``.
            raw_artifacts: Redacted ``raw/`` snapshot. defaults to ``egg.raw_artifacts``.
                required for ``passthrough`` when empty on the egg.

        Returns:
            ``HatchResult`` with paths and written files.
        """
        from pynydus.engine.hatcher import hatch as engine_hatch

        secrets_path = Path(secrets) if secrets else None
        return engine_hatch(
            egg,
            target=target,
            output_dir=output_dir,
            secrets_path=secrets_path,
            mode=mode,
            llm_config=self._config.llm,
            spawn_log=spawn_log,
            raw_artifacts=raw_artifacts,
        )

    def save(
        self,
        egg: Egg,
        output: Path,
        *,
        raw_artifacts: dict[str, str] | None = None,
        spawn_log: list[dict] | None = None,
        nydusfile_text: str | None = None,
        sign: bool = False,
    ) -> Path:
        """Write an Egg to a ``.egg`` archive.

        Args:
            egg: The Egg to save.
            output: Destination file path (gets ``.egg`` suffix).
            raw_artifacts: Override ``egg.raw_artifacts`` for the archive.
            spawn_log: Override ``egg.spawn_log`` for the archive.
            nydusfile_text: Embed Nydusfile text in the archive.
            sign: If ``True``, sign with the user's Ed25519 private key.

        Returns:
            Path to the written ``.egg`` file.
        """
        from pynydus.engine.packager import save as save_egg

        private_key = None
        if sign:
            from pynydus.security.signing import load_private_key

            private_key = load_private_key()

        return save_egg(
            egg,
            output,
            raw_artifacts=raw_artifacts,
            spawn_log=spawn_log,
            nydusfile_text=nydusfile_text,
            private_key=private_key,
        )

    def load(self, egg_path: Path, *, include_raw: bool = True) -> Egg:
        """Load a ``.egg`` archive into a fully populated :class:`~pynydus.api.schemas.Egg`.

        Args:
            egg_path: Path to the ``.egg`` file.
            include_raw: If ``False``, ``raw/`` is not read into ``egg.raw_artifacts``
                (empty dict). Use for large eggs when only structured modules are needed.
                for passthrough hatch, load with ``include_raw=True`` or pass
                ``read_raw_artifacts(egg_path)`` to :meth:`hatch`.

        Returns:
            Fully populated Egg with spawn_log, raw_artifacts, and nydusfile.
        """
        from pynydus.engine.packager import load as load_egg

        return load_egg(egg_path, include_raw=include_raw)

    def validate(self, egg: Egg) -> ValidationReport:
        """Validate structural integrity of an Egg.

        Args:
            egg: Egg to check.

        Returns:
            Report with errors and warnings.
        """
        from pynydus.engine.validator import validate_egg

        return validate_egg(egg)

    def diff(self, egg_a: Egg, egg_b: Egg) -> DiffReport:
        """Compare two Eggs.

        Args:
            egg_a: First Egg.
            egg_b: Second Egg.

        Returns:
            Structured diff report.
        """
        from pynydus.engine.differ import diff_eggs

        return diff_eggs(egg_a, egg_b)

    def push(
        self,
        egg_path: Path,
        *,
        name: str,
        version: str | None = None,
        author: str | None = None,
    ) -> dict:
        """Push a packed ``.egg`` to the Nest registry.

        Args:
            egg_path: Packed archive path.
            name: Registry name (e.g. ``user/my-agent``).
            version: Semver. if ``None``, taken from ``egg.manifest.egg_version``.
            author: Optional author override.

        Returns:
            Server JSON response body.
        """
        egg_path = Path(egg_path)
        if version is None:
            from pynydus.engine.packager import _unpack_egg_core

            egg = _unpack_egg_core(egg_path)
            version = egg.manifest.egg_version

        client = self._get_registry_client()
        return client.push(egg_path, name=name, version=version, author=author)

    def pull(
        self,
        name: str,
        *,
        version: str = "latest",
        output: Path = Path("pulled.egg"),
    ) -> Path:
        """Pull an Egg from the Nest registry.

        Args:
            name: Registry name (e.g. ``user/my-agent``).
            version: Semver tag. default ``latest``.
            output: Destination path for the downloaded ``.egg``.

        Returns:
            Path written on disk.
        """
        client = self._get_registry_client()
        return client.pull(name, version=version, output_path=output)

    def list_versions(self, name: str) -> list[dict]:
        """List published versions for *name*.

        Args:
            name: Registry-qualified egg name.

        Returns:
            List of version metadata dicts from the server.
        """
        client = self._get_registry_client()
        return client.list_versions(name)

    def _get_registry_client(self):  # noqa: ANN202
        """Build a ``NestClient`` from ``NYDUS_REGISTRY_URL``."""
        from pynydus.api.errors import ConfigError
        from pynydus.remote.registry import NestClient

        if self._config.registry is None:
            raise ConfigError(
                "Registry not configured. Set NYDUS_REGISTRY_URL (and optionally "
                "NYDUS_REGISTRY_AUTHOR)."
            )
        return NestClient(
            self._config.registry.url,
            author=self._config.registry.author,
        )
