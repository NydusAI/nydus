"""Structural diff between two Eggs."""

from __future__ import annotations

from pydantic import BaseModel

from pynydus.api.schemas import DiffEntry, DiffReport, Egg, ManifestChange
from pynydus.common.enums import Bucket, DiffChange


def diff_eggs(egg_a: Egg, egg_b: Egg) -> DiffReport:
    """Compare two Eggs and return a structured diff report.

    Compares manifest fields, skills, memory, and secrets.
    Records are matched by ``id``. For matched records, individual
    fields are compared. Unmatched records are reported as added/removed.
    """
    manifest_changes = _diff_manifest(egg_a, egg_b)
    entries: list[DiffEntry] = []

    entries.extend(
        _diff_records(
            list(egg_a.skills.skills),
            list(egg_b.skills.skills),
            bucket=Bucket.SKILL,
            compare_fields=["name", "content"],
        )
    )
    entries.extend(
        _diff_records(
            list(egg_a.memory.memory),
            list(egg_b.memory.memory),
            bucket=Bucket.MEMORY,
            compare_fields=["text", "label"],
        )
    )
    entries.extend(
        _diff_records(
            list(egg_a.secrets.secrets),
            list(egg_b.secrets.secrets),
            bucket=Bucket.SECRET,
            compare_fields=["placeholder", "kind", "name", "required_at_hatch"],
        )
    )

    identical = len(manifest_changes) == 0 and len(entries) == 0
    return DiffReport(identical=identical, manifest_changes=manifest_changes, entries=entries)


def _diff_manifest(egg_a: Egg, egg_b: Egg) -> list[ManifestChange]:
    """Compare manifest fields (skip created_at — always differs)."""
    changes: list[ManifestChange] = []
    fields = [
        "nydus_version",
        "egg_version",
        "agent_type",
        "included_modules",
    ]

    for field in fields:
        val_a = getattr(egg_a.manifest, field)
        val_b = getattr(egg_b.manifest, field)
        if val_a != val_b:
            changes.append(ManifestChange(field=field, old=str(val_a), new=str(val_b)))

    pol_a = egg_a.manifest.redaction_policy
    pol_b = egg_b.manifest.redaction_policy
    if pol_a != pol_b:
        changes.append(
            ManifestChange(
                field="redaction_policy",
                old=str(pol_a.model_dump() if pol_a else None),
                new=str(pol_b.model_dump() if pol_b else None),
            )
        )

    return changes


def _diff_records(
    a_list: list[BaseModel],
    b_list: list[BaseModel],
    bucket: Bucket,
    compare_fields: list[str],
) -> list[DiffEntry]:
    """Generic ID-based record comparison."""
    entries: list[DiffEntry] = []

    a_by_id: dict[str, BaseModel] = {getattr(r, "id"): r for r in a_list}
    b_by_id: dict[str, BaseModel] = {getattr(r, "id"): r for r in b_list}

    a_ids = set(a_by_id.keys())
    b_ids = set(b_by_id.keys())

    # Removed (in A but not B)
    for rid in sorted(a_ids - b_ids):
        rec = a_by_id[rid]
        name = getattr(rec, "name", None) or getattr(rec, "text", rid)
        # Truncate long text for display
        display = str(name)[:80]
        entries.append(
            DiffEntry(
                bucket=bucket,
                change=DiffChange.REMOVED,
                id=rid,
                old=display,
            )
        )

    # Added (in B but not A)
    for rid in sorted(b_ids - a_ids):
        rec = b_by_id[rid]
        name = getattr(rec, "name", None) or getattr(rec, "text", rid)
        display = str(name)[:80]
        entries.append(
            DiffEntry(
                bucket=bucket,
                change=DiffChange.ADDED,
                id=rid,
                new=display,
            )
        )

    # Modified (in both — compare fields)
    for rid in sorted(a_ids & b_ids):
        rec_a = a_by_id[rid]
        rec_b = b_by_id[rid]
        for field in compare_fields:
            val_a = getattr(rec_a, field)
            val_b = getattr(rec_b, field)
            if val_a != val_b:
                entries.append(
                    DiffEntry(
                        bucket=bucket,
                        change=DiffChange.MODIFIED,
                        id=rid,
                        field=field,
                        old=str(val_a)[:200],
                        new=str(val_b)[:200],
                    )
                )

    return entries
