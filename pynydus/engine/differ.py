"""Structural diff between two Eggs."""

from __future__ import annotations

from pydantic import BaseModel

from pynydus.api.schemas import DiffEntry, DiffReport, Egg


def diff_eggs(egg_a: Egg, egg_b: Egg) -> DiffReport:
    """Compare two Eggs and return a structured diff report.

    Compares manifest fields, skills, memory, and secrets.
    Records are matched by ``id``. For matched records, individual
    fields are compared. Unmatched records are reported as added/removed.
    """
    entries: list[DiffEntry] = []

    entries.extend(_diff_manifest(egg_a, egg_b))
    entries.extend(
        _diff_records(
            [s for s in egg_a.skills.skills],
            [s for s in egg_b.skills.skills],
            section="skills",
            compare_fields=["name", "content"],
        )
    )
    entries.extend(
        _diff_records(
            [m for m in egg_a.memory.memory],
            [m for m in egg_b.memory.memory],
            section="memory",
            compare_fields=["text", "label"],
        )
    )
    entries.extend(
        _diff_records(
            [s for s in egg_a.secrets.secrets],
            [s for s in egg_b.secrets.secrets],
            section="secrets",
            compare_fields=["placeholder", "kind", "name", "required_at_hatch"],
        )
    )

    return DiffReport(identical=len(entries) == 0, entries=entries)


def _diff_manifest(egg_a: Egg, egg_b: Egg) -> list[DiffEntry]:
    """Compare manifest fields (skip created_at — always differs)."""
    entries: list[DiffEntry] = []
    fields = [
        "nydus_version",
        "egg_version",
        "source_type",
        "source_connector",
        "build_intent",
        "included_modules",
    ]

    for field in fields:
        val_a = getattr(egg_a.manifest, field)
        val_b = getattr(egg_b.manifest, field)
        if val_a != val_b:
            entries.append(
                DiffEntry(
                    section="manifest",
                    change="modified",
                    field=field,
                    old=str(val_a),
                    new=str(val_b),
                )
            )

    # Compare redaction policy
    pol_a = egg_a.manifest.redaction_policy
    pol_b = egg_b.manifest.redaction_policy
    if pol_a != pol_b:
        entries.append(
            DiffEntry(
                section="manifest",
                change="modified",
                field="redaction_policy",
                old=str(pol_a.model_dump() if pol_a else None),
                new=str(pol_b.model_dump() if pol_b else None),
            )
        )

    return entries


def _diff_records(
    a_list: list[BaseModel],
    b_list: list[BaseModel],
    section: str,
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
                section=section,
                change="removed",
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
                section=section,
                change="added",
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
                        section=section,
                        change="modified",
                        id=rid,
                        field=field,
                        old=str(val_a)[:200],
                        new=str(val_b)[:200],
                    )
                )

    return entries
