"""Nydusfile DSL parser and static verifier. Spec §8."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pynydus.api.errors import NydusfileError
from pynydus.api.schemas import Bucket, PriorityHint, RedactMode, SourceType

_logger = logging.getLogger(__name__)

_VALID_SOURCES = {s.value for s in SourceType}
"""Source types accepted by SOURCE directives."""
_VALID_BUCKETS = {b.value for b in Bucket}
_VALID_REDACT = {r.value for r in RedactMode}
_VALID_PRIORITY = {p.value for p in PriorityHint}
_VALID_SECRET_POLICY = {"all_required", "none_required", "default"}

# Directives that may appear at most once.
_SINGULAR_DIRECTIVES = {
    "FROM", "INCLUDE", "EXCLUDE", "REDACT", "PURPOSE", "SECRET_POLICY",
}
# Directives that may appear multiple times.
_REPEATABLE_DIRECTIVES = {"PRIORITIZE", "EXCLUDE_FILES", "LABEL", "ADD", "SET", "REMOVE", "SOURCE"}


@dataclass
class SourceDirective:
    """A SOURCE directive from the Nydusfile."""

    source_type: str
    path: str


@dataclass
class MergeOp:
    """A single ADD/SET/REMOVE merge operation from the Nydusfile."""

    action: str  # "add", "set", "remove"
    bucket: str  # "memory", "skill", "secret"
    key: str  # identifier, label selector, file path, or secret name
    value: str = ""  # text content or file path for ADD/SET


@dataclass
class NydusfileConfig:
    """Parsed and verified Nydusfile configuration."""

    source: SourceType
    base_egg: str | None = None
    """Local file path to a base .egg archive for inheritance."""
    merge_ops: list[MergeOp] = field(default_factory=list)
    """ADD/SET/REMOVE operations to apply to the base egg."""
    include: set[Bucket] | None = None
    exclude: set[Bucket] | None = None
    redact: RedactMode = RedactMode.PII
    priorities: list[PriorityHint] = field(default_factory=list)
    purpose: str | None = None
    exclude_files: list[str] = field(default_factory=list)
    """Glob patterns for files to skip during source extraction."""
    custom_labels: dict[str, str] = field(default_factory=dict)
    """Manual label overrides: pattern → label. Applied during classification."""
    secret_policy: str = "default"
    """Controls required_at_hatch: 'all_required', 'none_required', or 'default'."""
    sources: list[SourceDirective] = field(default_factory=list)
    """Multi-source input: zero or more SOURCE directives."""

    @property
    def effective_buckets(self) -> set[Bucket]:
        """Compute the final set of included buckets."""
        base = self.include if self.include is not None else set(Bucket)
        if self.exclude:
            base = base - self.exclude
        return base


def parse(text: str) -> NydusfileConfig:
    """Parse a Nydusfile string and return a verified config.

    Raises NydusfileError on any syntax or verification failure.
    """
    base_egg: str | None = None
    merge_ops: list[MergeOp] = []
    include: set[Bucket] | None = None
    exclude: set[Bucket] | None = None
    redact: RedactMode = RedactMode.PII
    priorities: list[PriorityHint] = []
    purpose: str | None = None
    exclude_files: list[str] = []
    custom_labels: dict[str, str] = {}
    secret_policy: str = "default"
    sources: list[SourceDirective] = []
    seen: dict[str, int] = {}  # directive -> first line number

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(None, 1)
        directive = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        # --- Duplicate / unknown check ---
        if directive in _SINGULAR_DIRECTIVES:
            if directive in seen:
                raise NydusfileError(
                    f"Duplicate directive {directive} (first seen on line {seen[directive]})",
                    line=lineno,
                )
            seen[directive] = lineno
        elif directive in _REPEATABLE_DIRECTIVES:
            pass  # multiple allowed
        else:
            raise NydusfileError(f"Unknown directive '{parts[0]}'", line=lineno)

        # --- Parse each directive ---
        if directive == "FROM":
            if not arg:
                raise NydusfileError("FROM requires an egg reference", line=lineno)
            val = arg.strip()

            _is_egg_ref = (
                val.endswith(".egg")
                or "/" in val
                or "\\" in val
                or ":" in val
            )
            if _is_egg_ref:
                base_egg = val
                continue

            val_lower = val.lower()
            if val_lower in {s.value for s in SourceType}:
                raise NydusfileError(
                    f"FROM no longer accepts source types. "
                    f"Use SOURCE {val_lower} <path> instead.",
                    line=lineno,
                )
            raise NydusfileError(
                f"Invalid egg reference '{val}'. "
                f"FROM accepts a local egg path (e.g., ./base.egg) "
                f"or a versioned egg ref (e.g., nydus/openclaw:0.2.0).",
                line=lineno,
            )

        elif directive == "INCLUDE":
            include = _parse_bucket_list(arg, lineno)

        elif directive == "EXCLUDE":
            exclude = _parse_bucket_list(arg, lineno)

        elif directive == "REDACT":
            if not arg:
                raise NydusfileError("REDACT requires a mode", line=lineno)
            val = arg.strip().lower()
            if val not in _VALID_REDACT:
                raise NydusfileError(
                    f"Unknown redaction mode '{val}'. "
                    f"Expected one of: {', '.join(sorted(_VALID_REDACT))}",
                    line=lineno,
                )
            redact = RedactMode(val)

        elif directive == "PRIORITIZE":
            if not arg:
                raise NydusfileError("PRIORITIZE requires a hint", line=lineno)
            val = arg.strip().lower()
            if val not in _VALID_PRIORITY:
                raise NydusfileError(
                    f"Unknown priority hint '{val}'. "
                    f"Expected one of: {', '.join(sorted(_VALID_PRIORITY))}",
                    line=lineno,
                )
            priorities.append(PriorityHint(val))

        elif directive == "PURPOSE":
            if not arg:
                raise NydusfileError("PURPOSE requires a quoted string", line=lineno)
            stripped = arg.strip()
            if not (stripped.startswith('"') and stripped.endswith('"')):
                raise NydusfileError("PURPOSE value must be a quoted string", line=lineno)
            purpose = stripped[1:-1]

        elif directive == "EXCLUDE_FILES":
            if not arg:
                raise NydusfileError("EXCLUDE_FILES requires a glob pattern", line=lineno)
            exclude_files.append(arg.strip())

        elif directive == "LABEL":
            if not arg:
                raise NydusfileError("LABEL requires 'pattern label'", line=lineno)
            label_parts = arg.strip().split(None, 1)
            if len(label_parts) < 2:
                raise NydusfileError(
                    "LABEL requires two arguments: pattern and label "
                    "(e.g., LABEL soul.md system)",
                    line=lineno,
                )
            custom_labels[label_parts[0]] = label_parts[1]

        elif directive == "SECRET_POLICY":
            if not arg:
                raise NydusfileError("SECRET_POLICY requires a policy", line=lineno)
            val = arg.strip().lower()
            if val not in _VALID_SECRET_POLICY:
                raise NydusfileError(
                    f"Unknown secret policy '{val}'. "
                    f"Expected one of: {', '.join(sorted(_VALID_SECRET_POLICY))}",
                    line=lineno,
                )
            secret_policy = val

        elif directive == "SOURCE":
            if not arg:
                raise NydusfileError("SOURCE requires type and path (e.g., SOURCE openclaw ./data)", line=lineno)
            src_parts = arg.strip().split(None, 1)
            if len(src_parts) < 2:
                raise NydusfileError(
                    "SOURCE requires two arguments: type and path "
                    "(e.g., SOURCE openclaw ./data)",
                    line=lineno,
                )
            src_type = src_parts[0].lower()
            src_path = src_parts[1]
            if src_type not in _VALID_SOURCES:
                raise NydusfileError(
                    f"Unknown source type '{src_type}' for SOURCE. "
                    f"Expected one of: {', '.join(sorted(_VALID_SOURCES))}",
                    line=lineno,
                )
            # Check for duplicate source_type+path pairs
            new_src = SourceDirective(source_type=src_type, path=src_path)
            for existing in sources:
                if existing.source_type == new_src.source_type and existing.path == new_src.path:
                    raise NydusfileError(
                        f"Duplicate SOURCE: {src_type} {src_path}",
                        line=lineno,
                    )
            sources.append(new_src)

        elif directive == "ADD":
            op = _parse_merge_op("add", arg, lineno)
            merge_ops.append(op)

        elif directive == "SET":
            op = _parse_merge_op("set", arg, lineno)
            merge_ops.append(op)

        elif directive == "REMOVE":
            op = _parse_merge_op("remove", arg, lineno)
            merge_ops.append(op)

    # --- Verification ---
    if base_egg is None and not sources:
        raise NydusfileError(
            "Nydusfile must have at least one SOURCE directive or a FROM base egg"
        )

    # Contradiction: same bucket in both INCLUDE and EXCLUDE
    if include is not None and exclude is not None:
        overlap = include & exclude
        if overlap:
            raise NydusfileError(
                f"Contradictory include/exclude: {', '.join(b.value for b in overlap)}"
            )

    # PII safety warning
    if redact == RedactMode.NONE:
        _logger.warning("PII will not be redacted (REDACT none)")

    # Merge ops require a base egg
    if merge_ops and base_egg is None:
        raise NydusfileError("ADD/SET/REMOVE directives require a base egg (FROM path/to/base.egg)")

    if sources:
        effective_source = SourceType(sources[0].source_type)
    else:
        effective_source = SourceType.OPENCLAW  # placeholder; resolved from base egg at spawn time

    return NydusfileConfig(
        source=effective_source,
        base_egg=base_egg,
        merge_ops=merge_ops,
        include=include,
        exclude=exclude,
        redact=redact,
        priorities=priorities,
        purpose=purpose,
        exclude_files=exclude_files,
        custom_labels=custom_labels,
        secret_policy=secret_policy,
        sources=sources,
    )


def parse_file(path: str) -> NydusfileConfig:
    """Parse a Nydusfile from a file path."""
    from pathlib import Path

    text = Path(path).read_text()
    return parse(text)


def _parse_bucket_list(arg: str, lineno: int) -> set[Bucket]:
    """Parse a comma-separated bucket list."""
    if not arg.strip():
        raise NydusfileError("Expected bucket list (skills, memory, secrets)", line=lineno)
    buckets: set[Bucket] = set()
    for token in arg.split(","):
        val = token.strip().lower()
        if val not in _VALID_BUCKETS:
            raise NydusfileError(
                f"Unknown bucket '{val}'. Expected one of: {', '.join(sorted(_VALID_BUCKETS))}",
                line=lineno,
            )
        buckets.add(Bucket(val))
    return buckets


_VALID_MERGE_BUCKETS = {"memory", "skill", "secret"}


def _parse_merge_op(action: str, arg: str, lineno: int) -> MergeOp:
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
            f"{action.upper()} requires arguments: bucket [key] [value]",
            line=lineno,
        )

    parts = arg.strip().split(None, 1)
    bucket_spec = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    # Parse bucket and optional selector (e.g., "memory.label=X")
    if "." in bucket_spec:
        bucket, selector = bucket_spec.split(".", 1)
    else:
        bucket = bucket_spec
        selector = ""

    if bucket not in _VALID_MERGE_BUCKETS:
        raise NydusfileError(
            f"Unknown bucket '{bucket}' for {action.upper()}. "
            f"Expected one of: {', '.join(sorted(_VALID_MERGE_BUCKETS))}",
            line=lineno,
        )

    if action == "remove":
        # REMOVE bucket key  OR  REMOVE bucket.selector
        key = selector or rest.strip()
        if not key:
            raise NydusfileError(
                f"REMOVE requires an identifier (e.g., REMOVE skill my_skill)",
                line=lineno,
            )
        return MergeOp(action="remove", bucket=bucket, key=key)

    if action == "set":
        if not selector:
            raise NydusfileError(
                f"SET requires a selector (e.g., SET memory.label=facts \"new text\")",
                line=lineno,
            )
        if not rest:
            raise NydusfileError(
                f"SET requires a value (e.g., SET memory.label=facts \"new text\")",
                line=lineno,
            )
        value = _unquote(rest.strip())
        return MergeOp(action="set", bucket=bucket, key=selector, value=value)

    # ADD
    if not rest:
        raise NydusfileError(
            f"ADD requires content or a file path",
            line=lineno,
        )
    value = _unquote(rest.strip())
    key = selector  # may be empty for simple adds
    return MergeOp(action="add", bucket=bucket, key=key, value=value)


def _unquote(s: str) -> str:
    """Remove surrounding double quotes from a string if present."""
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s
