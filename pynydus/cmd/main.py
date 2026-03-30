"""Nydus CLI — Typer application. Spec §17."""

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
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Output Egg path")
    ] = Path("./agent.egg"),
    config_path: Annotated[
        Path | None,
        typer.Option("-c", "--config", help="Path to config file (default: ./config.json)"),
    ] = None,
) -> None:
    """Create an Egg from source artifacts.

    Reads a Nydusfile from the current directory. The Nydusfile must contain
    at least one SOURCE directive declaring the input type and path.
    """
    from pynydus.engine.nydusfile import parse_file
    from pynydus.engine.packager import pack_with_raw
    from pynydus.engine.pipeline import build as engine_spawn
    from pynydus.pkg.config import load_config

    nydusfile_path = (Path.cwd() / "Nydusfile").resolve()
    if not nydusfile_path.exists():
        rprint(
            "[red]Error:[/red] No Nydusfile found in current directory.\n"
            "Create a Nydusfile with at least one SOURCE directive, e.g.:\n\n"
            "  SOURCE openclaw ./my-agent/\n"
            "  REDACT pii"
        )
        raise typer.Exit(1)

    nydus_cfg = load_config(config_path)
    nydusfile_dir = nydusfile_path.parent

    try:
        nydusfile_config = parse_file(str(nydusfile_path))
        egg, raw_artifacts, logs = engine_spawn(
            nydusfile_dir,
            nydusfile_config=nydusfile_config,
            llm_config=nydus_cfg.llm,
            nydusfile_dir=nydusfile_dir,
        )
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    private_key = None
    try:
        from pynydus.pkg.signing import load_private_key

        private_key = load_private_key()
    except Exception:
        pass

    nydusfile_text = nydusfile_path.read_text()

    spawn_log = logs.get("spawn_log", [])
    egg_path = pack_with_raw(
        egg,
        output,
        raw_artifacts,
        spawn_log=spawn_log,
        nydusfile_text=nydusfile_text,
        private_key=private_key,
    )
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
        if counts.get("redaction"):
            parts.append(f"{counts['redaction']} redactions")
        if counts.get("classification"):
            parts.append(f"{counts['classification']} auto-labels")
        if counts.get("extraction"):
            parts.append(f"{counts['extraction']} value extractions")
        if parts:
            rprint(f"  [dim]logs: {', '.join(parts)}[/dim]")


# ---------------------------------------------------------------------------
# hatch
# ---------------------------------------------------------------------------


@app.command()
def hatch(
    egg_path: Annotated[Path, typer.Argument(help="Path to .egg file")],
    target: Annotated[
        str, typer.Option("--target", help="Target runtime")
    ] = ...,  # type: ignore[assignment]
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Output directory")
    ] = Path("./agent/"),
    secrets: Annotated[
        Path | None,
        typer.Option("--secrets", help="Path to .env substitution file"),
    ] = None,
    reconstruct: Annotated[
        bool, typer.Option("--reconstruct", help="Force regeneration from modules")
    ] = False,
    config_path: Annotated[
        Path | None,
        typer.Option("-c", "--config", help="Path to config file (default: ./config.json)"),
    ] = None,
) -> None:
    """Deploy an Egg into a target runtime."""
    from pynydus.engine.hatcher import hatch as engine_hatch
    from pynydus.engine.packager import read_logs, read_raw_artifacts, unpack, verify_egg_archive
    from pynydus.pkg.config import load_config

    nydus_cfg = load_config(config_path)

    # Verify signature before hatching
    sig_status = verify_egg_archive(egg_path)
    if sig_status is False:
        rprint("[red]Error:[/red] Egg signature is INVALID — the egg may have been tampered with.")
        raise typer.Exit(1)
    if sig_status is True:
        rprint("[green]Signature verified.[/green]")
    # sig_status is None → unsigned, proceed silently

    # Read spawn log and raw artifacts from the archive
    spawn_log = read_logs(egg_path).get("spawn_log.json", [])
    raw_artifacts = read_raw_artifacts(egg_path)

    try:
        egg = unpack(egg_path)
        result = engine_hatch(
            egg,
            target=target,
            output_dir=output,
            secrets_path=secrets,
            reconstruct=reconstruct,
            llm_config=nydus_cfg.llm,
            spawn_log=spawn_log or None,
            raw_artifacts=raw_artifacts or None,
        )
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    rprint(f"[green]Hatched into {target}:[/green] {result.output_dir}")
    for f in result.files_created:
        rprint(f"  {f}")
    for w in result.warnings:
        rprint(f"  [yellow]Warning:[/yellow] {w}")


# ---------------------------------------------------------------------------
# env
# ---------------------------------------------------------------------------


@app.command()
def env(
    egg_path: Annotated[Path, typer.Argument(help="Path to .egg file")],
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Output .env path")
    ] = Path("./hatch.env"),
) -> None:
    """Generate a template .env file from an egg's secrets."""
    from pynydus.engine.packager import unpack

    try:
        egg = unpack(egg_path)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    secrets = egg.secrets.secrets
    if not secrets:
        rprint("[dim]No secrets found in this egg — nothing to write.[/dim]")
        return

    lines = ["# Generated by nydus env", ""]
    for s in secrets:
        required = "required" if s.required_at_hatch else "optional"
        desc = s.description or s.name
        lines.append(f"# {desc} [{s.kind.value}] ({required})")
        lines.append(f"{s.name}=")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
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
    show_logs: Annotated[
        bool, typer.Option("--logs", help="Show pipeline log summary")
    ] = False,
) -> None:
    """Print Egg summary."""
    from pynydus.engine.packager import unpack, verify_egg_archive

    try:
        egg = unpack(egg_path)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    m = egg.manifest
    rprint(f"[bold]Egg:[/bold] {egg_path.name}")
    rprint(f"  nydus {m.nydus_version} | egg spec {m.egg_version} | requires >= {m.min_nydus_version}")
    rprint(f"  source: {m.source_type} ({m.source_connector})")
    if m.base_egg:
        rprint(f"  base egg: {m.base_egg}")
    rprint(f"  created: {m.created_at}")

    # Signature status
    sig_status = verify_egg_archive(egg_path)
    if sig_status is True:
        rprint("  signature: [green]valid[/green] (Ed25519)")
    elif sig_status is False:
        rprint("  signature: [red]INVALID — egg may be tampered[/red]")
    else:
        rprint("  signature: [dim]unsigned[/dim]")
    if m.build_intent:
        rprint(f"  intent: {m.build_intent}")
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
        from collections import Counter

        from pynydus.engine.packager import read_logs

        logs = read_logs(egg_path)
        spawn_log = logs.get("spawn_log.json", [])

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
        labels = Counter(e.get("assigned_label", "?") for e in entries)
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
    """Check Egg integrity."""
    from pynydus.engine.packager import unpack
    from pynydus.engine.validator import validate_egg

    try:
        egg = unpack(egg_path)
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
    """Compare two Eggs."""
    from pynydus.engine.differ import diff_eggs
    from pynydus.engine.packager import unpack

    try:
        a = unpack(egg_a)
        b = unpack(egg_b)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    report = diff_eggs(a, b)

    rprint(f"[bold]diff[/bold] {egg_a.name} <-> {egg_b.name}")

    if report.identical:
        rprint("[green]Eggs are identical.[/green]")
        return

    rprint(f"[yellow]{len(report.entries)} change(s) found.[/yellow]")

    # Group entries by section
    sections: dict[str, list] = {}
    for entry in report.entries:
        sections.setdefault(entry.section, []).append(entry)

    for section, entries in sections.items():
        rprint(f"\n  [bold]{section}[/bold]")
        for e in entries:
            id_str = f" {e.id}" if e.id else ""
            if e.change == "added":
                rprint(f"    [green]+[/green]{id_str}  {e.new}")
            elif e.change == "removed":
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
    """Delete an Egg."""
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
    """Generate an Ed25519 keypair for egg signing."""
    from pynydus.pkg.signing import generate_keypair

    priv_path, pub_path = generate_keypair(key_dir)
    rprint(f"[green]Keypair generated:[/green]")
    rprint(f"  private: {priv_path}")
    rprint(f"  public:  {pub_path}")
    rprint(f"  [dim]Private key permissions set to 600 (owner-only).[/dim]")


# ---------------------------------------------------------------------------
# push / pull (Phase 1b stubs)
# ---------------------------------------------------------------------------


@app.command()
def push(
    egg_path: Annotated[Path, typer.Argument(help="Path to .egg file")],
    name: Annotated[
        str, typer.Option("--name", help="Registry name (user/egg-name)")
    ] = ...,  # type: ignore[assignment]
    version: Annotated[
        str, typer.Option("--version", help="Version string (e.g. 0.1.0)")
    ] = ...,  # type: ignore[assignment]
    author: Annotated[
        str | None, typer.Option("--author", help="Author name")
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option("-c", "--config", help="Path to config file (default: ./config.json)"),
    ] = None,
) -> None:
    """Publish an Egg to the Nest registry."""
    from pynydus.remote.registry import NestClient
    from pynydus.pkg.config import load_config

    if not egg_path.exists():
        rprint(f"[red]Error:[/red] File not found: {egg_path}")
        raise typer.Exit(1)

    nydus_cfg = load_config(config_path)
    if nydus_cfg.registry is None:
        rprint(
            "[red]Error:[/red] Registry not configured. "
            "Add a 'registry' section to config.json with at least 'url'."
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
    version: Annotated[
        str, typer.Option("--version", help="Version to pull")
    ] = ...,  # type: ignore[assignment]
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Output path")
    ] = Path("pulled.egg"),
    config_path: Annotated[
        Path | None,
        typer.Option("-c", "--config", help="Path to config file (default: ./config.json)"),
    ] = None,
) -> None:
    """Download an Egg from the Nest registry."""
    from pynydus.remote.registry import NestClient
    from pynydus.pkg.config import load_config

    nydus_cfg = load_config(config_path)
    if nydus_cfg.registry is None:
        rprint(
            "[red]Error:[/red] Registry not configured. "
            "Add a 'registry' section to config.json with at least 'url'."
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
    config_path: Annotated[
        Path | None,
        typer.Option("-c", "--config", help="Path to config file (default: ./config.json)"),
    ] = None,
) -> None:
    """Register a new account on the Nest registry."""
    from pynydus.remote.registry import NestClient
    from pynydus.pkg.config import load_config

    nydus_cfg = load_config(config_path)
    if nydus_cfg.registry is None:
        rprint(
            "[red]Error:[/red] Registry not configured. "
            "Add a 'registry' section to config.json with at least 'url'."
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
    config_path: Annotated[
        Path | None,
        typer.Option("-c", "--config", help="Path to config file (default: ./config.json)"),
    ] = None,
) -> None:
    """Log in to the Nest registry and store credentials."""
    from pynydus.remote.registry import NestClient
    from pynydus.pkg.config import load_config

    nydus_cfg = load_config(config_path)
    if nydus_cfg.registry is None:
        rprint(
            "[red]Error:[/red] Registry not configured. "
            "Add a 'registry' section to config.json with at least 'url'."
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
def logout(
    config_path: Annotated[
        Path | None,
        typer.Option("-c", "--config", help="Path to config file (default: ./config.json)"),
    ] = None,
) -> None:
    """Log out from the Nest registry (remove stored credentials)."""
    from pynydus.remote.registry import NestClient
    from pynydus.pkg.config import load_config

    nydus_cfg = load_config(config_path)
    if nydus_cfg.registry is None:
        rprint(
            "[red]Error:[/red] Registry not configured. "
            "Add a 'registry' section to config.json with at least 'url'."
        )
        raise typer.Exit(1)

    client = NestClient(nydus_cfg.registry.url)
    removed = client.logout()

    if removed:
        rprint("[green]Logged out.[/green]")
    else:
        rprint("[dim]No stored credentials to remove.[/dim]")
