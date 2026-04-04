"""Nydusfile DSL parser and static verifier. Spec §8."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from pynydus.api.errors import NydusfileError
from pynydus.common.enums import (
    AgentType,
    Bucket,
    Directive,
    MemoryLabel,
)

_logger = logging.getLogger(__name__)


@dataclass
class SourceDirective:
    """A SOURCE directive from the Nydusfile."""

    agent_type: str
    path: str


@dataclass
class MergeOp:
    """A single ADD/SET/REMOVE merge operation from the Nydusfile."""

    action: Directive
    bucket: Bucket
    key: str
    value: str = ""


@dataclass
class NydusfileConfig:
    """Parsed and verified Nydusfile configuration."""

    base_egg: str | None = None
    """Local file path to a base .egg archive for inheritance."""
    merge_ops: list[MergeOp] = field(default_factory=list)
    """ADD/SET/REMOVE operations to apply to the base egg."""
    redact: bool = True
    """Whether to redact credentials and PII. Defaults to True."""
    excluded_memory_labels: list[MemoryLabel] = field(default_factory=list)
    """Memory buckets to drop after parse (repeatable ``EXCLUDE`` lines)."""
    custom_labels: dict[str, str] = field(default_factory=dict)
    """Manual label overrides: pattern → label. Applied during classification."""
    sources: list[SourceDirective] = field(default_factory=list)
    """At most one SOURCE directive (zero if FROM-only)."""
    source_remove_globs: list[str] = field(default_factory=list)
    """Glob patterns for source keys to drop before parse (``REMOVE file <glob>``)."""


def parse(text: str) -> NydusfileConfig:
    """Parse a Nydusfile string and return a verified config.

    Raises NydusfileError on any syntax or verification failure.
    """
    base_egg: str | None = None
    merge_ops: list[MergeOp] = []
    redact: bool = True
    excluded_memory_labels: list[MemoryLabel] = []
    custom_labels: dict[str, str] = {}
    sources: list[SourceDirective] = []
    source_remove_globs: list[str] = []
    seen: dict[Directive, int] = {}

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(None, 1)
        arg = parts[1] if len(parts) > 1 else ""

        try:
            directive = Directive(parts[0].upper())
        except ValueError:
            raise NydusfileError(f"Unknown directive '{parts[0]}'", line=lineno)

        # --- Duplicate check ---
        if directive.is_singular:
            if directive in seen:
                raise NydusfileError(
                    f"Duplicate directive {directive} (first seen on line {seen[directive]})",
                    line=lineno,
                )
            seen[directive] = lineno

        # --- Parse each directive ---
        if directive is Directive.FROM:
            if not arg:
                raise NydusfileError("FROM requires an egg reference", line=lineno)
            val = arg.strip()
            try:
                AgentType(val.lower())
            except ValueError:
                base_egg = val
                continue
            raise NydusfileError(
                f"FROM no longer accepts source types. Use SOURCE {val.lower()} <path> instead.",
                line=lineno,
            )

        elif directive is Directive.REDACT:
            if not arg:
                raise NydusfileError("REDACT requires true or false", line=lineno)
            val = arg.strip().lower()
            if val not in ("true", "false"):
                raise NydusfileError(
                    f"Invalid REDACT value '{val}'. Expected 'true' or 'false'.",
                    line=lineno,
                )
            redact = val == "true"

        elif directive is Directive.EXCLUDE:
            if not arg:
                raise NydusfileError(
                    "EXCLUDE requires a memory label (persona, flow, context, or state)",
                    line=lineno,
                )
            token = arg.strip().split(None, 1)[0]
            try:
                excluded_memory_labels.append(MemoryLabel(token.lower()))
            except ValueError:
                raise NydusfileError(
                    f"Unknown memory label '{token}' for EXCLUDE. "
                    f"Expected one of: {', '.join(sorted(MemoryLabel))}",
                    line=lineno,
                )

        elif directive is Directive.LABEL:
            if not arg:
                raise NydusfileError("LABEL requires 'pattern label'", line=lineno)
            label_parts = arg.strip().split(None, 1)
            if len(label_parts) < 2:
                raise NydusfileError(
                    "LABEL requires two arguments: pattern and label (e.g., LABEL soul.md persona)",
                    line=lineno,
                )
            pattern, label_str = label_parts[0], label_parts[1]
            if pattern in custom_labels:
                raise NydusfileError(
                    f"Duplicate LABEL for pattern '{pattern}'",
                    line=lineno,
                )
            try:
                MemoryLabel(label_str)
            except ValueError:
                raise NydusfileError(
                    f"Unknown label '{label_str}'. "
                    f"Expected one of: {', '.join(sorted(MemoryLabel))}",
                    line=lineno,
                )
            custom_labels[pattern] = label_str

        elif directive is Directive.SOURCE:
            if not arg:
                raise NydusfileError(
                    "SOURCE requires type and path (e.g., SOURCE openclaw ./data)", line=lineno
                )
            src_parts = arg.strip().split(None, 1)
            if len(src_parts) < 2:
                raise NydusfileError(
                    "SOURCE requires two arguments: type and path (e.g., SOURCE openclaw ./data)",
                    line=lineno,
                )
            src_type = src_parts[0].lower()
            src_path = src_parts[1]
            try:
                AgentType(src_type)
            except ValueError:
                raise NydusfileError(
                    f"Unknown agent type '{src_type}' for SOURCE. "
                    f"Expected one of: {', '.join(sorted(AgentType))}",
                    line=lineno,
                )
            if sources:
                raise NydusfileError(
                    "Only one SOURCE directive is allowed. Combine inputs under one directory "
                    "or use separate Nydusfiles.",
                    line=lineno,
                )
            new_src = SourceDirective(agent_type=src_type, path=src_path)
            sources.append(new_src)

        elif directive.is_merge:
            if directive is Directive.REMOVE and _is_remove_file_directive(arg):
                pat = _parse_remove_file_pattern(arg, lineno)
                source_remove_globs.append(pat)
            else:
                merge_ops.append(_parse_merge_op(directive, arg, lineno))

    # --- Verification ---
    if base_egg is None and not sources:
        raise NydusfileError("Nydusfile must have at least one SOURCE directive or a FROM base egg")

    # PII safety warning
    if not redact:
        _logger.warning(
            "Redaction disabled (REDACT false). PII and credentials will not be redacted."
        )

    # Merge ops require a base egg
    if merge_ops and base_egg is None:
        raise NydusfileError("ADD/SET/REMOVE directives require a base egg (FROM path/to/base.egg)")

    if source_remove_globs and not sources:
        raise NydusfileError(
            "REMOVE file <glob> requires a SOURCE directive (no source tree to filter)"
        )

    return NydusfileConfig(
        base_egg=base_egg,
        merge_ops=merge_ops,
        redact=redact,
        excluded_memory_labels=excluded_memory_labels,
        custom_labels=custom_labels,
        sources=sources,
        source_remove_globs=source_remove_globs,
    )


def parse_file(path: str) -> NydusfileConfig:
    """Parse a Nydusfile from a file path."""
    text = Path(path).read_text()
    return parse(text)


def _is_remove_file_directive(arg: str) -> bool:
    if not arg or not arg.strip():
        return False
    return arg.strip().split(None, 1)[0].lower() == "file"


def _parse_remove_file_pattern(arg: str, lineno: int) -> str:
    parts = arg.strip().split(None, 1)
    if len(parts) < 2 or parts[0].lower() != "file":
        raise NydusfileError(
            "REMOVE file requires a glob pattern (e.g., REMOVE file *.log)",
            line=lineno,
        )
    pat = parts[1].strip()
    if not pat:
        raise NydusfileError(
            "REMOVE file requires a glob pattern (e.g., REMOVE file *.log)",
            line=lineno,
        )
    return pat


def _parse_merge_op(action: Directive, arg: str, lineno: int) -> MergeOp:
    """Parse an ADD/SET/REMOVE directive argument.

    Supported forms:
    - ``ADD memory "text content"``
    - ``ADD memory ./file.md``
    - ``ADD skill ./file.md``
    - ``ADD secret SECRET_NAME``
    - ``SET memory.label=X "new value"``
    - ``REMOVE skill skill_name``
    - ``REMOVE memory.label=X``
    """
    if not arg:
        raise NydusfileError(
            f"{action} requires arguments: bucket [key] [value]",
            line=lineno,
        )

    parts = arg.strip().split(None, 1)
    bucket_spec = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if "." in bucket_spec:
        raw_bucket, selector = bucket_spec.split(".", 1)
    else:
        raw_bucket = bucket_spec
        selector = ""

    try:
        bucket = Bucket(raw_bucket)
    except ValueError:
        raise NydusfileError(
            f"Unknown bucket '{raw_bucket}' for {action}. "
            f"Expected one of: {', '.join(sorted(Bucket))}",
            line=lineno,
        )

    if action is Directive.REMOVE:
        key = selector or rest.strip()
        if not key:
            raise NydusfileError(
                "REMOVE requires an identifier (e.g., REMOVE skill my_skill)",
                line=lineno,
            )
        return MergeOp(action=Directive.REMOVE, bucket=bucket, key=key)

    if action is Directive.SET:
        if bucket is Bucket.SECRET:
            raise NydusfileError(
                "SET is not supported for the secret bucket. Use REMOVE + ADD to replace a secret.",
                line=lineno,
            )
        if not selector:
            raise NydusfileError(
                'SET requires a selector (e.g., SET memory.label=facts "new text")',
                line=lineno,
            )
        if not rest:
            raise NydusfileError(
                'SET requires a value (e.g., SET memory.label=facts "new text")',
                line=lineno,
            )
        value = _unquote(rest.strip())
        return MergeOp(action=Directive.SET, bucket=bucket, key=selector, value=value)

    # ADD
    if not rest:
        raise NydusfileError(
            "ADD requires content or a file path",
            line=lineno,
        )
    value = _unquote(rest.strip())
    key = selector
    return MergeOp(action=Directive.ADD, bucket=bucket, key=key, value=value)


def _unquote(s: str) -> str:
    """Remove surrounding double quotes from a string if present."""
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


# ---------------------------------------------------------------------------
# Nydusfile discovery and default template generation
# ---------------------------------------------------------------------------


def resolve_nydusfile(directory: Path) -> Path:
    """Find or create a Nydusfile in the given directory.

    If no Nydusfile exists, auto-detects the agent type and writes
    a default Nydusfile from the corresponding template.
    """
    nydusfile = directory / "Nydusfile"
    if nydusfile.exists():
        return nydusfile

    agent_type = _auto_detect_for_template(directory)
    template = _load_default_template(agent_type)
    nydusfile.write_text(template)
    _logger.info("Created default Nydusfile for %s", agent_type)
    return nydusfile


def _auto_detect_for_template(directory: Path) -> AgentType:
    """Identify the agent type in *directory* by probing each spawner.

    All spawners are evaluated; if more than one matches, the layout is
    ambiguous and the user must add an explicit ``SOURCE <type> <path>``.
    """
    from pynydus.agents.letta.spawner import LettaSpawner
    from pynydus.agents.openclaw.spawner import OpenClawSpawner
    from pynydus.agents.zeroclaw.spawner import ZeroClawSpawner

    candidates: list[tuple[object, AgentType]] = [
        (OpenClawSpawner(), AgentType.OPENCLAW),
        (LettaSpawner(), AgentType.LETTA),
        (ZeroClawSpawner(), AgentType.ZEROCLAW),
    ]
    matches = [at for spawner, at in candidates if spawner.detect(directory)]

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(sorted(m.value for m in matches))
        raise NydusfileError(
            f"Ambiguous agent layout in {directory}: matches {names}. "
            "Create a Nydusfile with an explicit line such as "
            "'SOURCE openclaw ./' or 'SOURCE zeroclaw ./' (adjust type and path)."
        )
    raise NydusfileError(
        f"Cannot auto-detect agent type in {directory}. "
        "Create a Nydusfile manually with a SOURCE directive."
    )


def _load_default_template(agent_type: AgentType) -> str:
    """Load the Nydusfile.default template for *agent_type*."""
    template_path = (
        Path(__file__).resolve().parent.parent / "agents" / agent_type / "Nydusfile.default"
    )
    if not template_path.exists():
        raise NydusfileError(f"No default Nydusfile template for agent type '{agent_type}'")
    return template_path.read_text()
