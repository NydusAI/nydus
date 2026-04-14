"""Egg merge operations: apply ADD/SET/REMOVE directives to a base egg.

Implements local-only egg inheritance: load a base .egg archive, then apply
merge operations to produce a modified EggPartial.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pynydus.api.errors import HatchError, NydusfileError
from pynydus.api.schemas import (
    AgentSkill,
    Egg,
    EggPartial,
    McpModule,
    MemoryModule,
    MemoryRecord,
    SecretRecord,
    SecretsModule,
    SkillsModule,
)
from pynydus.common.enums import (
    Directive,
    InjectionMode,
    MemoryLabel,
    ModuleType,
    SecretKind,
)
from pynydus.engine.nydusfile import MergeOp

logger = logging.getLogger(__name__)


def load_base_egg(egg_path: str) -> Egg:
    """Load a base .egg archive from a local file path.

    Args:
        egg_path: Path to the ``.egg`` file on disk.

    Returns:
        Loaded Egg with structured modules.

    Raises:
        HatchError: If the file does not exist or cannot be unpacked.
    """
    path = Path(egg_path)
    if not path.exists():
        raise HatchError(f"Base egg not found: {egg_path}")

    from pynydus.engine.packager import _unpack_egg_core

    return _unpack_egg_core(path)


def merge(
    base_egg: Egg,
    ops: list[MergeOp],
    *,
    base_dir: Path | None = None,
) -> EggPartial:
    """Apply merge operations to a base egg and return the resulting EggPartial.

    Args:
        base_egg: Loaded base Egg.
        ops: Parsed ``ADD`` / ``SET`` / ``REMOVE`` operations.
        base_dir: Nydusfile directory. relative paths in values resolve here.

    Returns:
        Partial egg with merged modules.
    """
    partial = EggPartial(
        skills=SkillsModule(skills=list(base_egg.skills.skills)),
        mcp=McpModule(configs=dict(base_egg.mcp.configs)),
        memory=MemoryModule(memory=list(base_egg.memory.memory)),
        secrets=SecretsModule(secrets=list(base_egg.secrets.secrets)),
    )

    for op in ops:
        if op.action is Directive.ADD:
            _apply_add(partial, op, base_dir)
        elif op.action is Directive.SET:
            _apply_set(partial, op, base_dir)
        elif op.action is Directive.REMOVE:
            _apply_remove(partial, op)
        else:
            raise NydusfileError(f"Unknown merge action: {op.action}")

    return partial


def _apply_add(partial: EggPartial, op: MergeOp, base_dir: Path | None) -> None:
    """Add a new record to the specified bucket."""
    if op.bucket is ModuleType.MEMORY:
        text = _resolve_value(op.value, base_dir)
        label_str = _extract_label_from_key(op.key) if op.key else None
        try:
            label = MemoryLabel(label_str) if label_str else MemoryLabel.STATE
        except ValueError:
            label = MemoryLabel.STATE
        next_id = f"mem_{len(partial.memory.memory) + 1:03d}"
        partial.memory.memory.append(
            MemoryRecord(
                id=next_id,
                text=text,
                label=label,
                agent_type="nydusfile",
                source_store="merge_add",
            )
        )

    elif op.bucket is ModuleType.SKILL:
        text = _resolve_value(op.value, base_dir)
        name = op.key if op.key else _infer_skill_name(op.value)
        next_id = f"skill_{len(partial.skills.skills) + 1:03d}"
        partial.skills.skills.append(
            AgentSkill(
                name=name,
                body=text,
                metadata={"id": next_id, "source_framework": "merge_add"},
            )
        )

    elif op.bucket is ModuleType.SECRET:
        name = op.value.strip()
        next_id = f"secret_{len(partial.secrets.secrets) + 1:03d}"
        placeholder = f"{{{{{name}}}}}"
        partial.secrets.secrets.append(
            SecretRecord(
                id=next_id,
                placeholder=placeholder,
                kind=SecretKind.CREDENTIAL,
                name=name,
                required_at_hatch=True,
                injection_mode=InjectionMode.ENV,
                description="Added via Nydusfile merge",
            )
        )


def _apply_set(partial: EggPartial, op: MergeOp, base_dir: Path | None) -> None:
    """Replace all records matching the selector."""
    selector_key, selector_val = _parse_selector(op.key)
    new_text = _resolve_value(op.value, base_dir)
    matched = False

    if op.bucket is ModuleType.MEMORY:
        for i, rec in enumerate(partial.memory.memory):
            if _matches_selector(rec, selector_key, selector_val):
                partial.memory.memory[i] = rec.model_copy(update={"text": new_text})
                matched = True

    elif op.bucket is ModuleType.SKILL:
        for i, rec in enumerate(partial.skills.skills):
            if _matches_selector(rec, selector_key, selector_val):
                partial.skills.skills[i] = rec.model_copy(update={"body": new_text})
                matched = True

    if not matched:
        logger.warning(
            "SET %s.%s=%s: no matching record found", op.bucket, selector_key, selector_val
        )


def _apply_remove(partial: EggPartial, op: MergeOp) -> None:
    """Remove records matching the key/selector."""
    if op.bucket is ModuleType.MEMORY:
        if "=" in op.key:
            selector_key, selector_val = _parse_selector(op.key)
            partial.memory.memory = [
                r
                for r in partial.memory.memory
                if not _matches_selector(r, selector_key, selector_val)
            ]
        else:
            partial.memory.memory = [r for r in partial.memory.memory if r.id != op.key]

    elif op.bucket is ModuleType.SKILL:
        partial.skills.skills = [
            s
            for s in partial.skills.skills
            if s.name != op.key and s.metadata.get("id", "") != op.key
        ]

    elif op.bucket is ModuleType.SECRET:
        partial.secrets.secrets = [
            s for s in partial.secrets.secrets if s.name != op.key and s.id != op.key
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_value(value: str, base_dir: Path | None = None) -> str:
    """If value looks like a file path, read its contents. Otherwise return as-is.

    Relative paths are resolved against *base_dir* (the Nydusfile's directory).
    Raises ``NydusfileError`` if the value looks like a path but the file does
    not exist.
    """
    if not value.startswith(("./", "../", "/")):
        return value

    path = Path(value)
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / value

    if not path.exists():
        raise NydusfileError(f"File not found: {path}")
    if not path.is_file():
        raise NydusfileError(f"Not a file: {path}")
    return path.read_text()


def _parse_selector(selector: str) -> tuple[str, str]:
    """Parse ``key=value`` selector string."""
    if "=" not in selector:
        return ("name", selector)
    key, _, val = selector.partition("=")
    return (key.strip(), val.strip())


def _matches_selector(record: object, key: str, value: str) -> bool:
    """Check if a record matches a selector (attribute == value)."""
    actual = getattr(record, key, None)
    if actual is None:
        return False
    return str(actual) == value


def _extract_label_from_key(key: str) -> str | None:
    """Extract label from a key like 'label=fact'."""
    if "=" in key:
        k, _, v = key.partition("=")
        if k.strip() == "label":
            return v.strip()
    return key if key else None


def _infer_skill_name(value: str) -> str:
    """Infer a skill name from a file path or text."""
    if value.startswith("./") or value.startswith("/"):
        return Path(value).stem.replace("_", " ").replace("-", " ")
    return "unnamed skill"
