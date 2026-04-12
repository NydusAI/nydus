"""Validation at each pipeline stage. Spec §20."""

from __future__ import annotations

from pynydus.api.schemas import Egg, ValidationIssue, ValidationReport


def validate_egg(egg: Egg) -> ValidationReport:
    """Validate an Egg's structural integrity.

    Args:
        egg: The Egg to validate.

    Returns:
        Report with ``valid`` flag and any issues found.
    """
    issues: list[ValidationIssue] = []

    # Check manifest required fields
    if not egg.manifest.nydus_version:
        issues.append(ValidationIssue(level="error", message="Missing nydus_version in manifest"))
    if not egg.manifest.agent_type:
        issues.append(ValidationIssue(level="error", message="Missing agent_type in manifest"))
    if not egg.manifest.included_modules:
        issues.append(ValidationIssue(level="warning", message="No modules listed in manifest"))
    if not egg.manifest.signature:
        issues.append(
            ValidationIssue(
                level="warning",
                message="Egg is unsigned (no signature in manifest)",
            )
        )

    # Check that secrets have no live values
    for secret in egg.secrets.secrets:
        if secret.value_present:
            issues.append(
                ValidationIssue(
                    level="error",
                    message=f"Secret {secret.id} has value_present=true",
                    location=f"secrets.json:{secret.id}",
                )
            )

    # Check skill IDs are unique
    skill_ids = [s.id for s in egg.skills.skills]
    if len(skill_ids) != len(set(skill_ids)):
        issues.append(ValidationIssue(level="error", message="Duplicate skill IDs found"))

    # Check memory IDs are unique
    mem_ids = [m.id for m in egg.memory.memory]
    if len(mem_ids) != len(set(mem_ids)):
        issues.append(ValidationIssue(level="error", message="Duplicate memory IDs found"))

    # Check skill_ref references resolve to actual skills
    skill_names = {s.name for s in egg.skills.skills}
    for m in egg.memory.memory:
        if m.skill_ref and m.skill_ref not in skill_names:
            issues.append(
                ValidationIssue(
                    level="warning",
                    message=f"Memory {m.id} references unknown skill: {m.skill_ref}",
                    location=f"memory.json:{m.id}",
                )
            )

    return ValidationReport(
        valid=not any(i.level == "error" for i in issues),
        issues=issues,
    )
