"""Nydus CLI: Typer application.

Entry point for ``nydus`` commands: spawn, hatch, inspect, diff,
registry operations, and key management.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import print as rprint
from rich.table import Table

app = typer.Typer(
    name="nydus",
    help="Portable state transport for AI agents.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# spawn
# ---------------------------------------------------------------------------


@app.command()
def spawn(
    output: Annotated[Path, typer.Option("-o", "--output", help="Output Egg path")] = Path(
        "./agent.egg"
    ),
) -> None:
    """Create an Egg from source artifacts.

    Discovers a Nydusfile in the current directory, then runs the spawning
    pipeline to produce an Egg.

    Args:
        output: Path for the written ``.egg`` archive (default ``./agent.egg``).
    """
    from pynydus.config import load_config
    from pynydus.engine.nydusfile import parse_file, resolve_nydusfile
    from pynydus.engine.packager import save
    from pynydus.engine.pipeline import spawn as engine_spawn

    nydus_cfg = load_config()

    try:
        nydusfile_path = resolve_nydusfile(Path.cwd())
        nydusfile_dir = nydusfile_path.parent
        config = parse_file(str(nydusfile_path))
        egg, raw_artifacts, logs = engine_spawn(
            config,
            nydusfile_dir=nydusfile_dir,
            llm_config=nydus_cfg.llm,
        )
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    private_key = None
    try:
        from pynydus.security.signing import load_private_key

        private_key = load_private_key()
    except Exception:
        pass

    nydusfile_text = nydusfile_path.read_text()

    spawn_log = logs.get("spawn_log", [])
    egg = egg.model_copy(
        update={
            "raw_artifacts": raw_artifacts,
            "spawn_log": spawn_log,
            "nydusfile": nydusfile_text,
        }
    )
    egg_path = save(egg, output, private_key=private_key)
    rprint(f"[green]Egg spawned:[/green] {egg_path}")
    rprint(
        f"  skills={len(egg.skills.skills)}  "
        f"memory={len(egg.memory.memory)}  "
        f"secrets={len(egg.secrets.secrets)}"
    )
    if private_key:
        rprint("  [green]signed[/green] (Ed25519)")
    else:
        rprint("  [dim]unsigned (run 'nydus keygen' to enable signing)[/dim]")
    # Summary of pipeline activity
    if spawn_log:
        from collections import Counter

        counts = Counter(entry["type"] for entry in spawn_log)
        parts = []
        if counts.get("secret_scan"):
            parts.append(f"{counts['secret_scan']} secret detections")
        if counts.get("redaction"):
            parts.append(f"{counts['redaction']} redactions")
        if counts.get("classification"):
            parts.append(f"{counts['classification']} auto-labels")
        if counts.get("extraction"):
            parts.append(f"{counts['extraction']} value extractions")
        if parts:
            rprint(f"  [dim]logs: {', '.join(parts)}[/dim]")
    if nydus_cfg.llm is None:
        rprint(
            "  [dim]LLM refinement disabled "
            "(set NYDUS_LLM_TYPE and NYDUS_LLM_API_KEY to enable)[/dim]"
        )


# ---------------------------------------------------------------------------
# hatch
# ---------------------------------------------------------------------------


@app.command()
def hatch(
    egg_path: Annotated[Path, typer.Argument(help="Path to .egg file")],
    target: Annotated[str, typer.Option("--target", help="Target runtime")] = ...,  # type: ignore[assignment]
    output: Annotated[Path, typer.Option("-o", "--output", help="Output directory")] = Path(
        "./agent/"
    ),
    secrets: Annotated[
        Path | None,
        typer.Option("--secrets", help="Path to .env substitution file"),
    ] = None,
    passthrough: Annotated[
        bool,
        typer.Option(
            "--passthrough", help="Replay redacted raw/ snapshot instead of rebuilding from modules"
        ),
    ] = False,
) -> None:
    """Deploy an Egg into a target runtime.

    Args:
        egg_path: Path to the ``.egg`` file.
        target: Destination runtime (e.g. ``openclaw``, ``letta``, ``zeroclaw``).
        output: Output directory for hatched files.
        secrets: Optional ``.env`` path for placeholder substitution at hatch.
        passthrough: When set, replay ``raw/`` instead of rebuilding from modules.
    """
    from pynydus.common.enums import AgentType, HatchMode
    from pynydus.config import load_config
    from pynydus.engine.hatcher import hatch as engine_hatch
    from pynydus.engine.packager import load, verify_egg_archive

    nydus_cfg = load_config()

    # Fail fast on tampered eggs before doing any disk I/O
    sig_status = verify_egg_archive(egg_path)
    if sig_status is False:
        rprint(
            "[red]Error:[/red] Egg signature is invalid. The archive may have been tampered with."
        )
        raise typer.Exit(1)
    if sig_status is True:
        rprint("[green]Signature verified.[/green]")
    # sig_status is None → unsigned, proceed silently

    try:
        egg = load(egg_path)
        result = engine_hatch(
            egg,
            target=AgentType(target),
            output_dir=output,
            secrets_path=secrets,
            mode=HatchMode.PASSTHROUGH if passthrough else HatchMode.REBUILD,
            llm_config=nydus_cfg.llm,
        )
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    rprint(f"[green]Hatched into {target}:[/green] {result.output_dir}")
    for f in result.files_created:
        rprint(f"  {f}")
    for w in result.warnings:
        rprint(f"  [yellow]Warning:[/yellow] {w}")
    if nydus_cfg.llm is None:
        rprint(
            "  [dim]LLM refinement disabled "
            "(set NYDUS_LLM_TYPE and NYDUS_LLM_API_KEY to enable)[/dim]"
        )


# ---------------------------------------------------------------------------
# env
# ---------------------------------------------------------------------------


@app.command()
def env(
    egg_path: Annotated[Path, typer.Argument(help="Path to .egg file")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output .env path")] = Path(
        "./hatch.env"
    ),
) -> None:
    """Generate a template .env file from an egg's secrets.

    Args:
        egg_path: Path to the ``.egg`` file.
        output: Path for the generated ``.env`` template.
    """
    from pynydus.engine.packager import _unpack_egg_core

    try:
        egg = _unpack_egg_core(egg_path)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    secrets = egg.secrets.secrets
    if not secrets:
        rprint("[dim]No secrets found in this egg: nothing to write.[/dim]")
        return

    lines = ["# Generated by nydus env", ""]
    for s in secrets:
        required = "required" if s.required_at_hatch else "optional"
        desc = s.description or s.name
        lines.append(f"# {desc} [{s.kind.value}] ({required})")
        lines.append(f"{s.name}=")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rprint(f"[green]Wrote {output}[/green] ({len(secrets)} secret(s))")


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


@app.command()
def inspect(
    egg_path: Annotated[Path, typer.Argument(help="Path to .egg file")],
    show_secrets: Annotated[
        bool, typer.Option("--secrets", help="List all placeholders and occurrences")
    ] = False,
    show_logs: Annotated[bool, typer.Option("--logs", help="Show pipeline log summary")] = False,
) -> None:
    """Print Egg summary.

    Args:
        egg_path: Path to the ``.egg`` file.
        show_secrets: List placeholders and occurrence counts.
        show_logs: Print a grouped summary of ``spawn_log`` entries.
    """
    from pynydus.engine.packager import load, verify_egg_archive

    try:
        egg = load(egg_path)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    m = egg.manifest
    rprint(f"[bold]Egg:[/bold] {egg_path.name}")
    rprint(
        f"  nydus {m.nydus_version} | egg spec {m.egg_version} | requires >= {m.min_nydus_version}"
    )
    rprint(f"  agent type: {m.agent_type}")
    if m.base_egg:
        rprint(f"  base egg: {m.base_egg}")
    rprint(f"  created: {m.created_at}")

    sig_status = verify_egg_archive(egg_path)
    if sig_status is True:
        rprint("  signature: [green]valid[/green] (Ed25519)")
    elif sig_status is False:
        rprint("  signature: [red]INVALID: egg may be tampered[/red]")
    else:
        rprint("  signature: [dim]unsigned[/dim]")
    rprint(
        f"  skills={len(egg.skills.skills)}  "
        f"memory={len(egg.memory.memory)}  "
        f"secrets={len(egg.secrets.secrets)}"
    )

    if show_secrets and egg.secrets.secrets:
        rprint()
        table = Table(title="Secrets & Placeholders")
        table.add_column("Placeholder")
        table.add_column("Kind")
        table.add_column("Name")
        table.add_column("Required")
        table.add_column("Occurrences")
        for s in egg.secrets.secrets:
            table.add_row(
                s.placeholder,
                s.kind.value,
                s.name,
                "yes" if s.required_at_hatch else "no",
                str(len(s.occurrences)),
            )
        rprint(table)

    if show_logs:
        spawn_log = egg.spawn_log

        if not spawn_log:
            rprint("\n  [dim]No pipeline logs recorded.[/dim]")
        else:
            _print_log_summary("Spawn Log", spawn_log)


def _print_log_summary(title: str, entries: list[dict]) -> None:
    """Print a grouped summary table for a list of typed log entries."""
    if not entries:
        return

    from collections import Counter

    rprint()
    table = Table(title=title)
    table.add_column("Type")
    table.add_column("Count", justify="right")
    table.add_column("Details")

    by_type = Counter(e.get("type", "unknown") for e in entries)

    for entry_type, count in by_type.most_common():
        typed_entries = [e for e in entries if e.get("type") == entry_type]
        detail = _log_type_detail(entry_type, typed_entries)
        table.add_row(entry_type, str(count), detail)

    rprint(table)


def _log_type_detail(entry_type: str, entries: list[dict]) -> str:
    """Generate a detail string for a group of same-type log entries."""
    from collections import Counter

    if entry_type == "redaction":
        pii_types = Counter(e.get("pii_type", "?") for e in entries)
        return ", ".join(f"{v} {k}" for k, v in pii_types.most_common())

    if entry_type == "classification":
        labels = Counter(e.get("label", "?") for e in entries)
        return ", ".join(f"{v} {k}" for k, v in labels.most_common())

    if entry_type == "extraction":
        all_types: list[str] = []
        for e in entries:
            all_types.extend(e.get("types", []))
        type_counts = Counter(all_types)
        return ", ".join(f"{v} {k}" for k, v in type_counts.most_common())

    if entry_type == "llm_call":
        providers = Counter(e.get("provider", "?") for e in entries)
        total_ms = sum(e.get("latency_ms", 0) for e in entries)
        parts = [f"{v} {k}" for k, v in providers.most_common()]
        if total_ms:
            parts.append(f"{total_ms}ms total")
        return ", ".join(parts)

    return ""


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@app.command()
def validate(
    egg_path: Annotated[Path, typer.Argument(help="Path to .egg file")],
) -> None:
    """Check Egg integrity.

    Args:
        egg_path: Path to the ``.egg`` file.
    """
    from pynydus.engine.packager import _unpack_egg_core
    from pynydus.engine.validator import validate_egg

    try:
        egg = _unpack_egg_core(egg_path)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    report = validate_egg(egg)
    if report.valid:
        rprint("[green]Egg is valid.[/green]")
    else:
        rprint("[red]Egg is invalid.[/red]")
        for issue in report.issues:
            color = "red" if issue.level == "error" else "yellow"
            loc = f" ({issue.location})" if issue.location else ""
            rprint(f"  [{color}]{issue.level}:[/{color}] {issue.message}{loc}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


@app.command()
def diff(
    egg_a: Annotated[Path, typer.Argument(help="First Egg")],
    egg_b: Annotated[Path, typer.Argument(help="Second Egg")],
) -> None:
    """Compare two Eggs.

    Args:
        egg_a: Path to the first ``.egg`` file.
        egg_b: Path to the second ``.egg`` file.
    """
    from pynydus.common.enums import DiffChange
    from pynydus.engine.differ import diff_eggs
    from pynydus.engine.packager import _unpack_egg_core

    try:
        a = _unpack_egg_core(egg_a)
        b = _unpack_egg_core(egg_b)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    report = diff_eggs(a, b)

    rprint(f"[bold]diff[/bold] {egg_a.name} <-> {egg_b.name}")

    if report.identical:
        rprint("[green]Eggs are identical.[/green]")
        return

    total = len(report.manifest_changes) + len(report.entries)
    rprint(f"[yellow]{total} change(s) found.[/yellow]")

    if report.manifest_changes:
        rprint("\n  [bold]manifest[/bold]")
        for mc in report.manifest_changes:
            rprint(f"    [yellow]~[/yellow]  {mc.field}: {mc.old} → {mc.new}")

    by_bucket: dict[str, list] = {}
    for entry in report.entries:
        by_bucket.setdefault(entry.bucket, []).append(entry)

    for bucket, entries in by_bucket.items():
        rprint(f"\n  [bold]{bucket}[/bold]")
        for e in entries:
            id_str = f" {e.id}" if e.id else ""
            if e.change == DiffChange.ADDED:
                rprint(f"    [green]+[/green]{id_str}  {e.new}")
            elif e.change == DiffChange.REMOVED:
                rprint(f"    [red]-[/red]{id_str}  {e.old}")
            else:
                rprint(f"    [yellow]~[/yellow]{id_str}  {e.field}: {e.old} → {e.new}")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@app.command()
def delete(
    egg_path: Annotated[Path, typer.Argument(help="Path to .egg file")],
) -> None:
    """Delete an Egg.

    Args:
        egg_path: Path to the ``.egg`` file to remove.
    """
    if not egg_path.exists():
        rprint(f"[red]Not found:[/red] {egg_path}")
        raise typer.Exit(1)
    egg_path.unlink()
    rprint(f"[green]Deleted:[/green] {egg_path}")


# ---------------------------------------------------------------------------
# keygen
# ---------------------------------------------------------------------------


@app.command()
def keygen(
    key_dir: Annotated[
        Path | None,
        typer.Option("--dir", help="Directory to write keys to"),
    ] = None,
) -> None:
    """Generate an Ed25519 keypair for egg signing.

    Args:
        key_dir: Directory for ``private.pem`` and ``public.pem`` (default ``~/.nydus/keys``).
    """
    from pynydus.security.signing import generate_keypair

    priv_path, pub_path = generate_keypair(key_dir)
    rprint("[green]Keypair generated:[/green]")
    rprint(f"  private: {priv_path}")
    rprint(f"  public:  {pub_path}")
    rprint("  [dim]Private key permissions set to 600 (owner-only).[/dim]")


# ---------------------------------------------------------------------------
# push / pull (Phase 1b stubs)
# ---------------------------------------------------------------------------


@app.command()
def push(
    egg_path: Annotated[Path, typer.Argument(help="Path to .egg file")],
    name: Annotated[str, typer.Option("--name", help="Registry name (user/egg-name)")] = ...,  # type: ignore[assignment]
    version: Annotated[str, typer.Option("--version", help="Version string (e.g. 0.1.0)")] = ...,  # type: ignore[assignment]
    author: Annotated[str | None, typer.Option("--author", help="Author name")] = None,
) -> None:
    """Publish an Egg to the Nest registry.

    Args:
        egg_path: Path to the ``.egg`` file to upload.
        name: Registry-qualified name (e.g. ``user/my-agent``).
        version: Semver string for this publish.
        author: Optional author override (otherwise env/default).
    """
    from pynydus.config import load_config
    from pynydus.remote.registry import NestClient

    if not egg_path.exists():
        rprint(f"[red]Error:[/red] File not found: {egg_path}")
        raise typer.Exit(1)

    nydus_cfg = load_config()
    if nydus_cfg.registry is None:
        rprint(
            "[red]Error:[/red] Registry not configured. "
            "Set NYDUS_REGISTRY_URL (and optionally NYDUS_REGISTRY_AUTHOR)."
        )
        raise typer.Exit(1)

    client = NestClient(
        nydus_cfg.registry.url,
        author=nydus_cfg.registry.author,
    )

    try:
        result = client.push(egg_path, name=name, version=version, author=author)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    rprint(f"[green]Pushed:[/green] {name}:{version}")
    rprint(f"  sha256: {result.get('sha256', 'n/a')}")
    rprint(f"  size: {result.get('size_bytes', 0)} bytes")


@app.command()
def pull(
    name: Annotated[str, typer.Argument(help="Registry name (user/egg-name)")],
    version: Annotated[str, typer.Option("--version", help="Version to pull")] = ...,  # type: ignore[assignment]
    output: Annotated[Path, typer.Option("-o", "--output", help="Output path")] = Path(
        "pulled.egg"
    ),
) -> None:
    """Download an Egg from the Nest registry.

    Args:
        name: Registry-qualified egg name.
        version: Semver tag to pull.
        output: Destination path for the downloaded ``.egg``.
    """
    from pynydus.config import load_config
    from pynydus.remote.registry import NestClient

    nydus_cfg = load_config()
    if nydus_cfg.registry is None:
        rprint(
            "[red]Error:[/red] Registry not configured. "
            "Set NYDUS_REGISTRY_URL (and optionally NYDUS_REGISTRY_AUTHOR)."
        )
        raise typer.Exit(1)

    client = NestClient(
        nydus_cfg.registry.url,
        author=nydus_cfg.registry.author,
    )

    try:
        saved = client.pull(name, version=version, output_path=output)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    rprint(f"[green]Pulled:[/green] {name}:{version} -> {saved}")


# ---------------------------------------------------------------------------
# Auth: register / login / logout
# ---------------------------------------------------------------------------


@app.command()
def register(
    username: Annotated[str, typer.Argument(help="Username for the Nest registry")],
    password: Annotated[
        str,
        typer.Option("--password", "-p", prompt=True, hide_input=True, help="Password"),
    ] = ...,  # type: ignore[assignment]
) -> None:
    """Register a new account on the Nest registry.

    Args:
        username: Desired username.
        password: Password (prompted if omitted).
    """
    from pynydus.config import load_config
    from pynydus.remote.registry import NestClient

    nydus_cfg = load_config()
    if nydus_cfg.registry is None:
        rprint(
            "[red]Error:[/red] Registry not configured. "
            "Set NYDUS_REGISTRY_URL (and optionally NYDUS_REGISTRY_AUTHOR)."
        )
        raise typer.Exit(1)

    client = NestClient(nydus_cfg.registry.url)

    try:
        client.register(username, password)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    rprint(f"[green]Registered:[/green] {username}")


@app.command()
def login(
    username: Annotated[str, typer.Argument(help="Username for the Nest registry")],
    password: Annotated[
        str,
        typer.Option("--password", "-p", prompt=True, hide_input=True, help="Password"),
    ] = ...,  # type: ignore[assignment]
) -> None:
    """Log in to the Nest registry and store credentials.

    Args:
        username: Registry username.
        password: Password (prompted if omitted).
    """
    from pynydus.config import load_config
    from pynydus.remote.registry import NestClient

    nydus_cfg = load_config()
    if nydus_cfg.registry is None:
        rprint(
            "[red]Error:[/red] Registry not configured. "
            "Set NYDUS_REGISTRY_URL (and optionally NYDUS_REGISTRY_AUTHOR)."
        )
        raise typer.Exit(1)

    client = NestClient(nydus_cfg.registry.url)

    try:
        client.login(username, password)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    rprint(f"[green]Logged in:[/green] {username}")


@app.command()
def logout() -> None:
    """Log out from the Nest registry (remove stored credentials)."""
    from pynydus.config import load_config
    from pynydus.remote.registry import NestClient

    nydus_cfg = load_config()
    if nydus_cfg.registry is None:
        rprint(
            "[red]Error:[/red] Registry not configured. "
            "Set NYDUS_REGISTRY_URL (and optionally NYDUS_REGISTRY_AUTHOR)."
        )
        raise typer.Exit(1)

    client = NestClient(nydus_cfg.registry.url)
    removed = client.logout()

    if removed:
        rprint("[green]Logged out.[/green]")
    else:
        rprint("[dim]No stored credentials to remove.[/dim]")
