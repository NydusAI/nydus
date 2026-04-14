"""Validation at each pipeline stage. Spec §20.

Orchestrates structural checks plus per-standard validators from
``pynydus.standards``.
"""

from __future__ import annotations

from pynydus.api.schemas import Egg, ValidationIssue, ValidationReport


def validate_egg(egg: Egg) -> ValidationReport:
    """Validate an Egg's structural integrity and per-standard compliance.

    Runs two layers:
      1. Structural checks (manifest fields, ID uniqueness, secrets)
      2. Per-standard schema validation (MCP, skills, A2A, AGENTS.md)

    Args:
        egg: The Egg to validate.

    Returns:
        Report with ``valid`` flag and any issues found.
    """
    issues: list[ValidationIssue] = []

    issues.extend(_validate_structural(egg))
    issues.extend(_validate_standards(egg))

    return ValidationReport(
        valid=not any(i.level == "error" for i in issues),
        issues=issues,
    )


def _validate_structural(egg: Egg) -> list[ValidationIssue]:
    """Core structural validation: manifest, secrets, IDs, references."""
    issues: list[ValidationIssue] = []

    if not egg.manifest.nydus_version:
        issues.append(ValidationIssue(level="error", message="Missing nydus_version in manifest"))
    if not egg.manifest.agent_type:
        issues.append(ValidationIssue(level="error", message="Missing agent_type in manifest"))

    for secret in egg.secrets.secrets:
        if secret.value_present:
            issues.append(
                ValidationIssue(
                    level="error",
                    message=f"Secret {secret.id} has value_present=true",
                    location=f"secrets.json:{secret.id}",
                )
            )

    skill_ids = [s.metadata.get("id", s.name) for s in egg.skills.skills]
    if len(skill_ids) != len(set(skill_ids)):
        issues.append(ValidationIssue(level="error", message="Duplicate skill IDs found"))

    mem_ids = [m.id for m in egg.memory.memory]
    if len(mem_ids) != len(set(mem_ids)):
        issues.append(ValidationIssue(level="error", message="Duplicate memory IDs found"))

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

    return issues


def _validate_standards(egg: Egg) -> list[ValidationIssue]:
    """Run per-standard validators (MCP, skills, A2A, AGENTS.md).

    Each standard module's ``validate()`` returns a list of issues.
    APM is excluded (pure passthrough, no validation).
    """
    from pynydus.standards import a2a, agents_md, mcp, skills

    issues: list[ValidationIssue] = []
    issues.extend(mcp.validate(egg))
    issues.extend(skills.validate(egg))
    issues.extend(a2a.validate(egg))
    issues.extend(agents_md.validate(egg))
    return issues
