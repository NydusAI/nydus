"""Tests for API schema construction, serialization, and defaults."""

from pynydus.api.schemas import (
    MemoryRecord,
    SecretRecord,
    ValidationReport,
)
from pynydus.common.enums import (
    InjectionMode,
    MemoryLabel,
    SecretKind,
)


class TestMemoryRecord:
    def test_with_label(self):
        m = MemoryRecord(
            id="mem_001",
            text="{{PII_001}} prefers concise summaries.",
            label=MemoryLabel.PERSONA,
            agent_type="openclaw",
            source_store="SOUL.md",
        )
        assert m.label == MemoryLabel.PERSONA
        assert m.shareable is True

    def test_label_from_string(self):
        m = MemoryRecord(
            id="mem_002",
            text="Some context.",
            label=MemoryLabel.CONTEXT,
            agent_type="letta",
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
