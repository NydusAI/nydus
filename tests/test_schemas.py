"""Tests for pynydus.api.schemas."""

from datetime import UTC, datetime

from pynydus.api.schemas import (
    Bucket,
    Egg,
    InjectionMode,
    Manifest,
    MemoryLabel,
    MemoryRecord,
    RedactMode,
    SecretKind,
    SecretRecord,
    SkillRecord,
    SourceType,
    ValidationReport,
)


class TestEnums:
    def test_source_types(self):
        assert SourceType.OPENCLAW == "openclaw"
        assert SourceType.LETTA == "letta"

    def test_buckets(self):
        assert set(Bucket) == {"skills", "memory", "secrets"}

    def test_redact_modes(self):
        assert RedactMode.PII == "pii"
        assert RedactMode.NONE == "none"


class TestSkillRecord:
    def test_minimal(self):
        s = SkillRecord(
            id="skill_001",
            name="summarize_docs",
            source_type="markdown_skill",
            content="Summarize a document into 5 bullets.",
        )
        assert s.id == "skill_001"
        assert s.attachments == []
        assert s.metadata == {}

    def test_with_attachments(self):
        s = SkillRecord(
            id="skill_002",
            name="analyze_image",
            source_type="binary_skill",
            content="Analyze uploaded images.",
            attachments=["attachments/template.png"],
            metadata={"path": "raw/skills.md"},
        )
        assert len(s.attachments) == 1


class TestMemoryRecord:
    def test_with_label(self):
        m = MemoryRecord(
            id="mem_001",
            text="{{PII_001}} prefers concise summaries.",
            label=MemoryLabel.PERSONA,
            source_framework="openclaw",
            source_store="soul.md",
        )
        assert m.label == MemoryLabel.PERSONA
        assert m.shareable is True

    def test_label_from_string(self):
        m = MemoryRecord(
            id="mem_002",
            text="Some context.",
            label=MemoryLabel.CONTEXT,
            source_framework="letta",
            source_store="memory_block",
        )
        assert m.label == MemoryLabel.CONTEXT


class TestSecretRecord:
    def test_credential(self):
        s = SecretRecord(
            id="secret_001",
            placeholder="{{SECRET_001}}",
            kind=SecretKind.CREDENTIAL,
            name="OPENAI_API_KEY",
            required_at_hatch=True,
            injection_mode=InjectionMode.ENV,
            description="Required for LLM provider access.",
            occurrences=["raw/config.yaml:12"],
        )
        assert s.value_present is False
        assert s.kind == "credential"

    def test_pii(self):
        s = SecretRecord(
            id="pii_001",
            placeholder="{{PII_001}}",
            kind=SecretKind.PII,
            pii_type="PERSON",
            name="USER_NAME",
            injection_mode=InjectionMode.SUBSTITUTION,
        )
        assert s.pii_type == "PERSON"


class TestManifest:
    def test_required_fields(self):
        m = Manifest(
            nydus_version="0.1.0",
            created_at=datetime.now(UTC),
            source_type=SourceType.OPENCLAW,
            included_modules=["skills", "memory", "secrets"],
        )
        assert m.egg_version == "2.0"
        assert m.build_intent is None


class TestEgg:
    def test_default_modules(self):
        egg = Egg(
            manifest=Manifest(
                nydus_version="0.1.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["skills"],
            )
        )
        assert egg.skills.skills == []
        assert egg.memory.memory == []
        assert egg.secrets.secrets == []


class TestValidationReport:
    def test_valid(self):
        r = ValidationReport(valid=True)
        assert r.issues == []

    def test_with_issues(self):
        r = ValidationReport(
            valid=False,
            issues=[{"level": "error", "message": "Missing manifest", "location": "manifest.json"}],
        )
        assert len(r.issues) == 1
