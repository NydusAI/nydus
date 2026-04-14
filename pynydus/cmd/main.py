"""Nydus CLI: Typer application.

Entry point for ``nydus`` commands: spawn, hatch, inspect, extract, diff,
registry operations, and key management. Validation is embedded in
``inspect`` and ``hatch``. There is no standalone ``validate`` command.
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


def _print_llm_status(llm_config) -> None:  # noqa: ANN001
    """Print LLM refinement status at the start of a pipeline command."""
    if llm_config is not None:
        rprint(f"  [green]LLM refinement: enabled ({llm_config.provider}/{llm_config.model})[/green]")
    else:
        rprint(
            "  [dim]LLM refinement: disabled "
            "(set NYDUS_LLM_TYPE and NYDUS_LLM_API_KEY to enable)[/dim]"
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
    rprint("[bold]Spawning egg...[/bold]")
    _print_llm_status(nydus_cfg.llm)

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
    except (FileNotFoundError, ValueError, TypeError):
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


# ---------------------------------------------------------------------------
# hatch
# ---------------------------------------------------------------------------


@app.command()
def hatch(
    egg_path: Annotated[Path, typer.Argument(help="Path to .egg file")],
    target: Annotated[str, typer.Option("-t", "--target", help="Target runtime")] = ...,  # type: ignore[assignment]
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Output directory (default: ./<target>/)"),
    ] = None,
    secrets: Annotated[
        Path | None,
        typer.Option("-s", "--secrets", help="Path to .env substitution file"),
    ] = None,
    passthrough: Annotated[
        bool,
        typer.Option(
            "-P",
            "--passthrough",
            help="Replay the egg's redacted raw/ snapshot instead of rebuilding from modules",
        ),
    ] = False,
    skip_validation: Annotated[
        bool,
        typer.Option("-S", "--skip-validation", help="Skip egg validation before hatching"),
    ] = False,
) -> None:
    """Deploy an Egg into a target runtime.

    Args:
        egg_path: Path to the ``.egg`` file.
        target: Destination runtime (e.g. ``openclaw``, ``letta``, ``zeroclaw``).
        output: Output directory for hatched files (default: ``./<target>/``).
        secrets: Optional ``.env`` path for placeholder substitution at hatch.
        passthrough: When set, replay the egg's ``raw/`` snapshot instead of rebuilding.
        skip_validation: When set, skip structural and per-standard validation.
    """
    from pynydus.common.enums import AgentType, HatchMode
    from pynydus.config import load_config
    from pynydus.engine.hatcher import hatch as engine_hatch
    from pynydus.engine.packager import load, verify_egg_archive
    from pynydus.engine.validator import validate_egg

    nydus_cfg = load_config()
    rprint(f"[bold]Hatching {egg_path.name} into {target}...[/bold]")
    _print_llm_status(nydus_cfg.llm)

    # Fail fast on tampered eggs before doing any disk I/O
    sig_status = verify_egg_archive(egg_path)
    if sig_status is False:
        rprint(
            "[red]Error:[/red] Egg signature is invalid. The archive may have been tampered with."
        )
        raise typer.Exit(1)
    if sig_status is True:
        rprint("  [green]Signature verified.[/green]")

    try:
        egg = load(egg_path)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if output is None:
        output = Path(f"./{target}/")

    # Validation gate: reject eggs with errors before hatching
    if not skip_validation:
        report = validate_egg(egg)
        if not report.valid:
            rprint("[red]Egg validation failed. Aborting hatch.[/red]")
            for issue in report.issues:
                color = "red" if issue.level == "error" else "yellow"
                loc = f" ({issue.location})" if issue.location else ""
                rprint(f"  [{color}]{issue.level}:[/{color}] {issue.message}{loc}")
            rprint("[dim]Use --skip-validation (-S) to hatch anyway.[/dim]")
            raise typer.Exit(1)

    # Interactive secret prompting when --secrets is not provided
    tmp_secrets_path: Path | None = None
    if secrets is None and egg.secrets.secrets:
        rprint(f"[yellow]This egg requires {len(egg.secrets.secrets)} secret(s).[/yellow]")
        env_lines: list[str] = []
        for s in egg.secrets.secrets:
            req = "required" if s.required_at_hatch else "optional"
            desc = s.description or s.pii_type or ""
            if desc:
                rprint(f"  [dim]{s.name}: {desc}[/dim]")
            value = typer.prompt(f"  {s.name} ({s.kind.value}, {req})")
            if not value.strip() and s.required_at_hatch:
                rprint(f"[red]Error:[/red] Required secret '{s.name}' cannot be empty.")
                raise typer.Exit(1)
            if value.strip():
                env_lines.append(f"{s.name}={value}")
        if env_lines:
            tmp_secrets_path = output / ".nydus_secrets.env"
            tmp_secrets_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_secrets_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
            secrets = tmp_secrets_path

    try:
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
    finally:
        if tmp_secrets_path and tmp_secrets_path.exists():
            tmp_secrets_path.unlink()

    std_files = [f for f in result.files_created if not f.startswith("agent/")]
    agent_files = [f for f in result.files_created if f.startswith("agent/")]

    rprint(f"[green]Hatched into {target}:[/green] {result.output_dir}")
    if std_files:
        rprint("  [bold]Standards:[/bold]")
        for f in std_files:
            rprint(f"    {f}")
    if agent_files:
        rprint("  [bold]Agent files (agent/):[/bold]")
        for f in agent_files:
            rprint(f"    {f.removeprefix('agent/')}")
    for w in result.warnings:
        rprint(f"  [yellow]Warning:[/yellow] {w}")


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
        bool, typer.Option("-s", "--secrets", help="List all placeholders and occurrences")
    ] = False,
    show_logs: Annotated[
        bool, typer.Option("-l", "--logs", help="Show pipeline log summary")
    ] = False,
    no_validate: Annotated[
        bool, typer.Option("-n", "--no-validate", help="Skip per-standard validation")
    ] = False,
) -> None:
    """Print Egg summary with inline validation.

    Args:
        egg_path: Path to the ``.egg`` file.
        show_secrets: List placeholders and occurrence counts.
        show_logs: Print a grouped summary of ``spawn_log`` entries.
        no_validate: When set, skip per-standard schema validation.
    """
    from pynydus.engine.packager import load, verify_egg_archive
    from pynydus.engine.validator import validate_egg

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
    if m.agent_name:
        rprint(f"  agent name: {m.agent_name}")
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

    standards: list[str] = []
    if egg.mcp.configs:
        standards.append(f"mcp={len(egg.mcp.configs)} server(s)")
    if egg.a2a_card is not None:
        standards.append("a2a=present")
    if egg.agents_md is not None:
        standards.append("agents.md=present")
    if egg.apm_yml is not None:
        standards.append("apm=present")
    if egg.spec_snapshots:
        standards.append(f"specs={len(egg.spec_snapshots)}")
    if standards:
        rprint(f"  {' | '.join(standards)}")

    if not no_validate:
        report = validate_egg(egg)
        errors = [i for i in report.issues if i.level == "error"]
        warnings = [i for i in report.issues if i.level == "warning"]

        if report.valid and not warnings:
            rprint("  validation: [green]passed[/green]")
        elif report.valid:
            rprint(f"  validation: [green]passed[/green] ({len(warnings)} warning(s))")
        else:
            rprint(
                f"  validation: [red]FAILED[/red] "
                f"({len(errors)} error(s), {len(warnings)} warning(s))"
            )

        for issue in report.issues:
            color = "red" if issue.level == "error" else "yellow"
            loc = f" ({issue.location})" if issue.location else ""
            rprint(f"    [{color}]{issue.level}:[/{color}] {issue.message}{loc}")

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
# extract
# ---------------------------------------------------------------------------

extract_app = typer.Typer(
    name="extract",
    help="Extract standard artifacts from an Egg.",
    no_args_is_help=True,
)
app.add_typer(extract_app, name="extract")


def _load_egg_for_extract(egg_path: Path) -> Egg:  # noqa: F821
    """Load an egg, handling errors consistently for all extract subcommands."""
    from pynydus.engine.packager import load

    if not egg_path.exists():
        rprint(f"[red]Error:[/red] File not found: {egg_path}")
        raise typer.Exit(1)
    try:
        return load(egg_path)
    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def _write_extracted(files: dict[str, str], output_dir: Path, label: str) -> None:
    """Write extracted files to disk and print summary."""
    if not files:
        rprint(f"[dim]No {label} found in this egg.[/dim]")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        fpath = output_dir / name
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
        rprint(f"  [green]wrote[/green] {fpath}")

    rprint(f"[green]Extracted {len(files)} {label} file(s).[/green]")


@extract_app.command("mcp")
def extract_mcp(
    egg_path: Annotated[Path, typer.Option("-f", "--from", help="Path to .egg file")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output directory")] = Path("."),
) -> None:
    """Extract MCP server configs (mcp.json)."""
    from pynydus.standards import mcp

    egg = _load_egg_for_extract(egg_path)
    _write_extracted(mcp.extract(egg), output, "MCP config")


@extract_app.command("skills")
def extract_skills(
    egg_path: Annotated[Path, typer.Option("-f", "--from", help="Path to .egg file")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output directory")] = Path("."),
) -> None:
    """Extract Agent Skills (SKILL.md files)."""
    from pynydus.standards import skills

    egg = _load_egg_for_extract(egg_path)
    _write_extracted(skills.extract(egg), output, "skills")


@extract_app.command("a2a")
def extract_a2a(
    egg_path: Annotated[Path, typer.Option("-f", "--from", help="Path to .egg file")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output directory")] = Path("."),
) -> None:
    """Extract A2A agent card (agent-card.json)."""
    from pynydus.standards import a2a

    egg = _load_egg_for_extract(egg_path)
    _write_extracted(a2a.extract(egg), output, "A2A agent card")


@extract_app.command("apm")
def extract_apm(
    egg_path: Annotated[Path, typer.Option("-f", "--from", help="Path to .egg file")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output directory")] = Path("."),
) -> None:
    """Extract APM manifest (apm.yml). Passthrough only."""
    from pynydus.standards import apm

    egg = _load_egg_for_extract(egg_path)
    _write_extracted(apm.extract(egg), output, "apm.yml")


@extract_app.command("agents")
def extract_agents(
    egg_path: Annotated[Path, typer.Option("-f", "--from", help="Path to .egg file")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output directory")] = Path("."),
) -> None:
    """Extract per-egg AGENTS.md deployment runbook."""
    from pynydus.standards import agents_md

    egg = _load_egg_for_extract(egg_path)
    _write_extracted(agents_md.extract(egg), output, "AGENTS.md")


@extract_app.command("specs")
def extract_specs(
    egg_path: Annotated[Path, typer.Option("-f", "--from", help="Path to .egg file")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output directory")] = Path(
        "./specs"
    ),
) -> None:
    """Extract embedded spec snapshots."""
    egg = _load_egg_for_extract(egg_path)
    if not egg.spec_snapshots:
        rprint("[dim]No spec snapshots found in this egg.[/dim]")
        return
    _write_extracted(egg.spec_snapshots, output, "spec snapshot")


@extract_app.command("all")
def extract_all(
    egg_path: Annotated[Path, typer.Option("-f", "--from", help="Path to .egg file")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output directory")] = Path(
        "./extracted"
    ),
) -> None:
    """Extract all standard artifacts at once."""
    from pynydus.standards import a2a, agents_md, apm, mcp, skills

    egg = _load_egg_for_extract(egg_path)
    total = 0

    for label, files in [
        ("MCP config", mcp.extract(egg)),
        ("skills", skills.extract(egg)),
        ("A2A agent card", a2a.extract(egg)),
        ("apm.yml", apm.extract(egg)),
        ("AGENTS.md", agents_md.extract(egg)),
    ]:
        if files:
            for name, content in files.items():
                fpath = output / name
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(content, encoding="utf-8")
                rprint(f"  [green]wrote[/green] {fpath}")
                total += 1

    if egg.spec_snapshots:
        specs_dir = output / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        for name, content in egg.spec_snapshots.items():
            fpath = specs_dir / name
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")
            rprint(f"  [green]wrote[/green] {fpath}")
            total += 1

    if total:
        rprint(f"[green]Extracted {total} file(s) total.[/green]")
    else:
        rprint("[dim]No standard artifacts found in this egg.[/dim]")


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
        typer.Option("-d", "--dir", help="Directory to write keys to"),
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
# push / pull / registry
# ---------------------------------------------------------------------------


@app.command()
def push(
    egg_path: Annotated[Path, typer.Argument(help="Path to .egg file")],
    name: Annotated[str, typer.Option("-n", "--name", help="Registry name (user/egg-name)")] = ...,  # type: ignore[assignment]
    version: Annotated[str, typer.Option("-v", "--version", help="Version string (e.g. 0.1.0)")] = ...,  # type: ignore[assignment]
    author: Annotated[str | None, typer.Option("-a", "--author", help="Author name")] = None,
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
    version: Annotated[str, typer.Option("-v", "--version", help="Version to pull")] = ...,  # type: ignore[assignment]
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
