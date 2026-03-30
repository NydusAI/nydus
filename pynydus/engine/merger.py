"""Egg merge operations — apply ADD/SET/REMOVE directives to a base egg.

Implements local-only egg inheritance: load a base .egg archive, then apply
merge operations to produce a modified EggPartial.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pynydus.api.errors import HatchError, NydusfileError
from pynydus.api.schemas import (
    Egg,
    EggPartial,
    InjectionMode,
    MemoryLabel,
    MemoryModule,
    MemoryRecord,
    SecretKind,
    SecretRecord,
    SecretsModule,
    SkillRecord,
    SkillsModule,
)
from pynydus.engine.nydusfile import MergeOp

logger = logging.getLogger(__name__)


def load_base_egg(egg_path: str) -> Egg:
    """Load a base .egg archive from a local file path.

    Raises ``HatchError`` if the file does not exist or cannot be unpacked.
    """
    path = Path(egg_path)
    if not path.exists():
        raise HatchError(f"Base egg not found: {egg_path}")

    from pynydus.engine.packager import unpack

    return unpack(path)


def merge(base_egg: Egg, ops: list[MergeOp]) -> EggPartial:
    """Apply merge operations to a base egg and return the resulting EggPartial.

    The base egg's skills, memory, and secrets are copied into a new EggPartial,
    then each operation is applied in order.
    """
    # Start with a copy of the base egg's data
    partial = EggPartial(
        skills=SkillsModule(skills=list(base_egg.skills.skills)),
        memory=MemoryModule(memory=list(base_egg.memory.memory)),
        secrets=SecretsModule(secrets=list(base_egg.secrets.secrets)),
        source_metadata=dict(base_egg.manifest.source_metadata),
    )

    for op in ops:
        if op.action == "add":
            _apply_add(partial, op)
        elif op.action == "set":
            _apply_set(partial, op)
        elif op.action == "remove":
            _apply_remove(partial, op)
        else:
            raise NydusfileError(f"Unknown merge action: {op.action}")

    return partial


def _apply_add(partial: EggPartial, op: MergeOp) -> None:
    """Add a new record to the specified bucket."""
    if op.bucket == "memory":
        # Value is either inline text or a file path
        text = _resolve_value(op.value)
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
                source_framework="nydusfile",
                source_store="merge_add",
            )
        )

    elif op.bucket == "skill":
        text = _resolve_value(op.value)
        name = op.key if op.key else _infer_skill_name(op.value)
        next_id = f"skill_{len(partial.skills.skills) + 1:03d}"
        partial.skills.skills.append(
            SkillRecord(
                id=next_id,
                name=name,
                source_type="merge_add",
                content=text,
            )
        )

    elif op.bucket == "secret":
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
                description=f"Added via Nydusfile merge",
            )
        )


def _apply_set(partial: EggPartial, op: MergeOp) -> None:
    """Replace a record matching the selector."""
    selector_key, selector_val = _parse_selector(op.key)
    new_text = _resolve_value(op.value)

    if op.bucket == "memory":
        for i, rec in enumerate(partial.memory.memory):
            if _matches_selector(rec, selector_key, selector_val):
                partial.memory.memory[i] = rec.model_copy(update={"text": new_text})
                return
        logger.warning("SET memory.%s=%s: no matching record found", selector_key, selector_val)

    elif op.bucket == "skill":
        for i, rec in enumerate(partial.skills.skills):
            if _matches_selector(rec, selector_key, selector_val):
                partial.skills.skills[i] = rec.model_copy(update={"content": new_text})
                return
        logger.warning("SET skill.%s=%s: no matching record found", selector_key, selector_val)


def _apply_remove(partial: EggPartial, op: MergeOp) -> None:
    """Remove records matching the key/selector."""
    if op.bucket == "memory":
        if "=" in op.key:
            selector_key, selector_val = _parse_selector(op.key)
            partial.memory.memory = [
                r for r in partial.memory.memory
                if not _matches_selector(r, selector_key, selector_val)
            ]
        else:
            partial.memory.memory = [
                r for r in partial.memory.memory if r.id != op.key
            ]

    elif op.bucket == "skill":
        partial.skills.skills = [
            s for s in partial.skills.skills
            if s.name != op.key and s.id != op.key
        ]

    elif op.bucket == "secret":
        partial.secrets.secrets = [
            s for s in partial.secrets.secrets
            if s.name != op.key and s.id != op.key
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_value(value: str) -> str:
    """If value looks like a file path, read its contents. Otherwise return as-is."""
    if value.startswith("./") or value.startswith("../") or value.startswith("/"):
        path = Path(value)
        if path.exists() and path.is_file():
            return path.read_text()
    return value


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
