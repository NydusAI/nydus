"""Python SDK — mirrors the CLI 1:1. Spec §19.

Usage::

    from pynydus import Nydus

    ny = Nydus()
    egg = ny.spawn()                          # reads ./Nydusfile
    egg = ny.spawn(nydusfile="path/to/Nydusfile")
    path = ny.pack(egg, output=Path("agent.egg"))

    egg = ny.unpack(Path("agent.egg"))
    egg.modules.skills      # list of SkillRecord
    egg.modules.memory      # list of MemoryRecord
    egg.inspect_secrets()

    result = ny.hatch(egg, target="letta")
"""

from __future__ import annotations

from pathlib import Path

from pynydus.api.schemas import (
    DiffReport,
    Egg,
    HatchResult,
    SpawnAttachments,
    ValidationReport,
)
from pynydus.pkg.config import NydusConfig, load_config


class Nydus:
    """Main SDK entry point.

    Parameters
    ----------
    config_path:
        Path to a ``config.json`` file. If ``None``, auto-loads from
        ``./config.json`` if it exists. LLM refinement is enabled when
        the config contains an ``llm`` section.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._config: NydusConfig = load_config(config_path)

    def spawn(
        self,
        nydusfile: Path | str | None = None,
    ) -> Egg:
        """Spawn an Egg from a Nydusfile.

        Parameters
        ----------
        nydusfile:
            Path to a Nydusfile.  If ``None``, reads ``./Nydusfile`` from the
            current working directory.

        Returns an :class:`Egg` with :attr:`~pynydus.api.schemas.Egg.spawn_attachments`
        set (raw artifacts and pipeline logs).  Call :meth:`pack` to save to disk.
        """
        from pynydus.engine.nydusfile import parse_file
        from pynydus.engine.pipeline import build as engine_spawn

        nydusfile_path = Path(nydusfile) if nydusfile else Path.cwd() / "Nydusfile"
        if not nydusfile_path.exists():
            raise FileNotFoundError(
                f"Nydusfile not found: {nydusfile_path}\n"
                "Create a Nydusfile with at least one SOURCE directive."
            )

        nydusfile_path = nydusfile_path.resolve()
        nydusfile_dir = nydusfile_path.parent
        nydusfile_config = parse_file(str(nydusfile_path))
        egg, raw_artifacts, logs = engine_spawn(
            nydusfile_dir,
            nydusfile_config=nydusfile_config,
            llm_config=self._config.llm,
            nydusfile_dir=nydusfile_dir,
        )

        egg.spawn_attachments = SpawnAttachments(raw_artifacts=raw_artifacts, logs=logs)
        return egg

    def hatch(
        self,
        egg: Egg,
        *,
        target: str,
        output_dir: Path | None = None,
        secrets: str | Path | None = None,
        reconstruct: bool = False,
        spawn_log: list[dict] | None = None,
        raw_artifacts: dict[str, str] | None = None,
    ) -> HatchResult:
        """Hatch an Egg into a target runtime.

        Pass ``spawn_log`` (from the spawn pipeline) to give the hatch-side
        LLM context about what happened during spawning (redactions,
        classifications, extractions).

        Pass ``raw_artifacts`` (from the egg archive's ``raw/`` directory)
        to enable true pass-through mode when source and target match, and
        to provide full context for LLM refinement.
        """
        from pynydus.engine.hatcher import hatch as engine_hatch

        secrets_path = Path(secrets) if secrets else None
        return engine_hatch(
            egg,
            target=target,
            output_dir=output_dir,
            secrets_path=secrets_path,
            reconstruct=reconstruct,
            llm_config=self._config.llm,
            spawn_log=spawn_log,
            raw_artifacts=raw_artifacts,
        )

    def pack(
        self,
        egg: Egg,
        output: Path,
        raw_artifacts: dict[str, str] | None = None,
        logs: dict[str, list[dict]] | None = None,
        *,
        sign: bool = False,
    ) -> Path:
        """Pack an Egg into a ``.egg`` archive.

        If ``raw_artifacts`` or ``logs`` are ``None``, they are pulled
        from :attr:`~pynydus.api.schemas.Egg.spawn_attachments` when set by
        :meth:`spawn`.
        Set ``sign=True`` to sign the egg with the user's Ed25519 private key.
        """
        from pynydus.engine.packager import pack_with_raw

        if raw_artifacts is None:
            raw_artifacts = (
                egg.spawn_attachments.raw_artifacts
                if egg.spawn_attachments is not None
                else {}
            )
        if logs is None:
            logs = (
                egg.spawn_attachments.logs
                if egg.spawn_attachments is not None
                else {}
            )

        private_key = None
        if sign:
            from pynydus.pkg.signing import load_private_key

            private_key = load_private_key()

        return pack_with_raw(
            egg,
            output,
            raw_artifacts,
            spawn_log=logs.get("spawn_log"),
            private_key=private_key,
        )

    def unpack(self, egg_path: Path) -> Egg:
        """Unpack a ``.egg`` archive into an Egg object."""
        from pynydus.engine.packager import unpack

        return unpack(egg_path)

    def validate(self, egg: Egg) -> ValidationReport:
        """Validate an Egg's structural integrity."""
        from pynydus.engine.validator import validate_egg

        return validate_egg(egg)

    def diff(self, egg_a: Egg, egg_b: Egg) -> DiffReport:
        """Compare two Eggs and return a structured diff report."""
        from pynydus.engine.differ import diff_eggs

        return diff_eggs(egg_a, egg_b)

    def push(
        self,
        egg_or_path: Egg | Path,
        *,
        name: str,
        version: str | None = None,
        author: str | None = None,
    ) -> dict:
        """Push an Egg to the Nest registry.

        Parameters
        ----------
        egg_or_path:
            An :class:`Egg` object or path to a packed ``.egg`` archive.
            If an Egg, it must be packed first.
        name:
            Registry name (e.g. ``user/my-agent``).
        version:
            Semver version string.  If ``None``, inferred from
            ``egg.manifest.egg_version``.
        author:
            Override the default author.
        """
        if isinstance(egg_or_path, Egg):
            if version is None:
                version = egg_or_path.manifest.egg_version
            from pynydus.api.errors import ConfigError

            raise ConfigError(
                "push() with an Egg object requires packing first. "
                "Use pack() to create an archive, then push the path."
            )
        egg_path = Path(egg_or_path)
        if version is None:
            from pynydus.engine.packager import unpack

            egg = unpack(egg_path)
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

        Parameters
        ----------
        name:
            Registry name (e.g. ``user/my-agent``).
        version:
            Semver version string.  Defaults to ``"latest"``.
        output:
            Where to save the downloaded egg.
        """
        client = self._get_registry_client()
        return client.pull(name, version=version, output_path=output)

    def list_versions(self, name: str) -> list[dict]:
        """List all versions of an egg in the registry."""
        client = self._get_registry_client()
        return client.list_versions(name)

    def _get_registry_client(self):  # noqa: ANN202
        """Get or create a NestClient from config."""
        from pynydus.api.errors import ConfigError
        from pynydus.remote.registry import NestClient

        if self._config.registry is None:
            raise ConfigError(
                "Registry not configured. Add a 'registry' section to config.json "
                "with at least 'url'."
            )
        return NestClient(
            self._config.registry.url,
            author=self._config.registry.author,
        )
