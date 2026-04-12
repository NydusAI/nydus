"""Tests for Egg structural validation: manifest fields, ID uniqueness, and secret integrity."""

from datetime import UTC, datetime

from pynydus.api.schemas import (
    Egg,
    Manifest,
    MemoryModule,
    MemoryRecord,
    SecretRecord,
    SecretsModule,
    SkillRecord,
    SkillsModule,
)
from pynydus.common.enums import (
    AgentType,
    Bucket,
    InjectionMode,
    MemoryLabel,
    SecretKind,
)
from pynydus.engine.validator import validate_egg

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(**overrides) -> Manifest:
    defaults = dict(
        nydus_version="0.1.0",
        created_at=datetime.now(UTC),
        agent_type=AgentType.OPENCLAW,
        included_modules=[Bucket.SKILL, Bucket.MEMORY, Bucket.SECRET],
    )
    defaults.update(overrides)
    return Manifest(**defaults)


def _make_egg(**overrides) -> Egg:
    defaults = dict(manifest=_make_manifest())
    defaults.update(overrides)
    return Egg(**defaults)


def _make_skill(id: str = "skill_001") -> SkillRecord:
    return SkillRecord(
        id=id,
        name="test_skill",
        agent_type="markdown_skill",
        content="Do a thing.",
    )


def _make_memory(id: str = "mem_001") -> MemoryRecord:
    return MemoryRecord(
        id=id,
        text="I like dark mode.",
        agent_type="openclaw",
        source_store="soul",
        label=MemoryLabel.PERSONA,
    )


def _make_memory_with_skill_ref(id: str, skill_ref: str) -> MemoryRecord:
    return MemoryRecord(
        id=id,
        text="Memory referencing a skill.",
        agent_type="openclaw",
        source_store="soul",
        label=MemoryLabel.STATE,
        skill_ref=skill_ref,
    )


def _make_secret(
    id: str = "sec_001",
    *,
    value_present: bool = False,
    required_at_hatch: bool = False,
) -> SecretRecord:
    return SecretRecord(
        id=id,
        placeholder=f"{{{{{id.upper()}}}}}",
        kind=SecretKind.CREDENTIAL,
        name=id.upper(),
        required_at_hatch=required_at_hatch,
        injection_mode=InjectionMode.ENV,
        description="Test secret",
        value_present=value_present,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestValidEggs:
    def test_minimal_valid_egg(self):
        egg = _make_egg()
        report = validate_egg(egg)
        assert report.valid is True
        errors = [i for i in report.issues if i.level == "error"]
        assert errors == []

    def test_unsigned_egg_warns(self):
        egg = _make_egg()
        report = validate_egg(egg)
        assert report.valid is True
        warnings = [i for i in report.issues if i.level == "warning"]
        assert any("unsigned" in w.message for w in warnings)

    def test_signed_egg_no_signature_warning(self):
        egg = _make_egg(manifest=_make_manifest(signature="abc123"))
        report = validate_egg(egg)
        warnings = [i for i in report.issues if i.level == "warning"]
        assert not any("unsigned" in w.message for w in warnings)

    def test_egg_with_populated_modules(self):
        egg = _make_egg(
            skills=SkillsModule(skills=[_make_skill("s1"), _make_skill("s2")]),
            memory=MemoryModule(memory=[_make_memory("m1"), _make_memory("m2")]),
            secrets=SecretsModule(secrets=[_make_secret("sec_1"), _make_secret("sec_2")]),
        )
        report = validate_egg(egg)
        assert report.valid is True
        errors = [i for i in report.issues if i.level == "error"]
        assert errors == []

    def test_egg_with_required_secrets_is_valid(self):
        """required_at_hatch=True is fine -- it just means the secret must be provided at hatch."""
        egg = _make_egg(
            secrets=SecretsModule(secrets=[_make_secret("api_key", required_at_hatch=True)]),
        )
        report = validate_egg(egg)
        assert report.valid is True


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------


class TestManifestValidation:
    def test_missing_nydus_version(self):
        egg = _make_egg(manifest=_make_manifest(nydus_version=""))
        report = validate_egg(egg)
        assert report.valid is False
        errors = [i for i in report.issues if i.level == "error"]
        assert any("nydus_version" in i.message for i in errors)

    def test_empty_included_modules_warns(self):
        egg = _make_egg(manifest=_make_manifest(included_modules=[]))
        report = validate_egg(egg)
        assert report.valid is True
        warnings = [i for i in report.issues if i.level == "warning"]
        assert any("modules" in i.message.lower() for i in warnings)


# ---------------------------------------------------------------------------
# Secret validation -- no live values in the egg
# ---------------------------------------------------------------------------


class TestSecretValidation:
    def test_value_present_true_is_error(self):
        """The whole point of Nydus: eggs must NOT contain actual secret values."""
        egg = _make_egg(
            secrets=SecretsModule(secrets=[_make_secret("leak", value_present=True)]),
        )
        report = validate_egg(egg)
        assert report.valid is False
        errors = [i for i in report.issues if i.level == "error"]
        assert len(errors) == 1
        assert "value_present" in errors[0].message
        assert "leak" in errors[0].message

    def test_multiple_leaked_secrets(self):
        egg = _make_egg(
            secrets=SecretsModule(
                secrets=[
                    _make_secret("leak_1", value_present=True),
                    _make_secret("clean_1", value_present=False),
                    _make_secret("leak_2", value_present=True),
                ]
            ),
        )
        report = validate_egg(egg)
        assert report.valid is False
        errors = [i for i in report.issues if i.level == "error"]
        assert len(errors) == 2
        error_ids = {e.message for e in errors}
        assert any("leak_1" in m for m in error_ids)
        assert any("leak_2" in m for m in error_ids)

    def test_value_present_location_field(self):
        egg = _make_egg(
            secrets=SecretsModule(secrets=[_make_secret("oops", value_present=True)]),
        )
        report = validate_egg(egg)
        errors = [i for i in report.issues if i.level == "error"]
        assert len(errors) == 1
        assert errors[0].location == "secrets.json:oops"


# ---------------------------------------------------------------------------
# Duplicate ID validation
# ---------------------------------------------------------------------------


class TestDuplicateIDs:
    def test_duplicate_skill_ids(self):
        egg = _make_egg(
            skills=SkillsModule(skills=[_make_skill("dup"), _make_skill("dup")]),
        )
        report = validate_egg(egg)
        assert report.valid is False
        assert any("Duplicate skill" in i.message for i in report.issues)

    def test_duplicate_memory_ids(self):
        egg = _make_egg(
            memory=MemoryModule(memory=[_make_memory("dup"), _make_memory("dup")]),
        )
        report = validate_egg(egg)
        assert report.valid is False
        assert any("Duplicate memory" in i.message for i in report.issues)

    def test_unique_skill_ids_ok(self):
        egg = _make_egg(
            skills=SkillsModule(skills=[_make_skill("s1"), _make_skill("s2"), _make_skill("s3")]),
        )
        report = validate_egg(egg)
        assert report.valid is True

    def test_unique_memory_ids_ok(self):
        egg = _make_egg(
            memory=MemoryModule(memory=[_make_memory("m1"), _make_memory("m2")]),
        )
        report = validate_egg(egg)
        assert report.valid is True


# ---------------------------------------------------------------------------
# skill_ref validation
# ---------------------------------------------------------------------------


class TestSkillRefValidation:
    def test_valid_skill_ref(self):
        egg = _make_egg(
            skills=SkillsModule(skills=[_make_skill("s1")]),
            memory=MemoryModule(memory=[_make_memory_with_skill_ref("m1", "test_skill")]),
        )
        report = validate_egg(egg)
        warnings = [i for i in report.issues if "unknown skill" in i.message]
        assert warnings == []

    def test_invalid_skill_ref_warns(self):
        egg = _make_egg(
            skills=SkillsModule(skills=[_make_skill("s1")]),
            memory=MemoryModule(memory=[_make_memory_with_skill_ref("m1", "nonexistent_skill")]),
        )
        report = validate_egg(egg)
        assert report.valid is True
        warnings = [i for i in report.issues if "unknown skill" in i.message]
        assert len(warnings) == 1
        assert "nonexistent_skill" in warnings[0].message
        assert warnings[0].location == "memory.json:m1"

    def test_none_skill_ref_no_warning(self):
        egg = _make_egg(
            memory=MemoryModule(memory=[_make_memory("m1")]),
        )
        report = validate_egg(egg)
        warnings = [i for i in report.issues if "unknown skill" in i.message]
        assert warnings == []


# ---------------------------------------------------------------------------
# Combined / edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_multiple_errors_all_reported(self):
        """Validator should collect ALL issues, not stop at the first."""
        egg = _make_egg(
            manifest=_make_manifest(nydus_version=""),
            skills=SkillsModule(skills=[_make_skill("dup"), _make_skill("dup")]),
            secrets=SecretsModule(secrets=[_make_secret("x", value_present=True)]),
        )
        report = validate_egg(egg)
        assert report.valid is False
        errors = [i for i in report.issues if i.level == "error"]
        assert len(errors) >= 3

    def test_empty_modules_valid(self):
        """An egg with zero skills, zero memory, zero secrets is structurally fine."""
        egg = _make_egg(
            skills=SkillsModule(skills=[]),
            memory=MemoryModule(memory=[]),
            secrets=SecretsModule(secrets=[]),
        )
        report = validate_egg(egg)
        assert report.valid is True

    def test_report_valid_flag_only_reflects_errors(self):
        """Warnings do NOT make valid=False."""
        egg = _make_egg(manifest=_make_manifest(included_modules=[]))
        report = validate_egg(egg)
        assert report.valid is True
        assert len(report.issues) > 0
        assert all(i.level == "warning" for i in report.issues)
