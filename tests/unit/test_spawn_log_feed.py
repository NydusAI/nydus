"""Tests for feeding spawn log to hatch LLM (Priority 3.2).

Verifies that spawn-time events are summarized and included in the
hatch refinement prompt.
"""

from __future__ import annotations

from pynydus.engine.refinement import _summarize_spawn_log


class TestSummarizeSpawnLog:
    def test_empty_log(self):
        assert _summarize_spawn_log([]) == ""

    def test_secret_scans_summarized(self):
        log = [
            {"type": "secret_scan", "tool": "gitleaks", "placeholder": "{{SECRET_001}}"},
        ]
        summary = _summarize_spawn_log(log)
        assert "1 secret detections" in summary
        assert "gitleaks" in summary

    def test_secret_scans_multiple(self):
        log = [
            {"type": "secret_scan", "tool": "gitleaks", "name": "GITHUB_PAT"},
            {"type": "secret_scan", "tool": "gitleaks", "name": "AWS_KEY"},
        ]
        summary = _summarize_spawn_log(log)
        assert "2 secret detections" in summary

    def test_redactions_summarized(self):
        log = [
            {"type": "redaction", "pii_type": "email", "source": "soul.md"},
            {"type": "redaction", "pii_type": "email", "source": "soul.md"},
            {"type": "redaction", "pii_type": "phone", "source": "knowledge.md"},
        ]
        summary = _summarize_spawn_log(log)
        assert "3 PII redactions" in summary
        assert "email" in summary
        assert "phone" in summary

    def test_classifications_summarized(self):
        log = [
            {"type": "classification", "label": "flow"},
            {"type": "classification", "label": "persona"},
            {"type": "classification", "label": "flow"},
        ]
        summary = _summarize_spawn_log(log)
        assert "3 auto-classifications" in summary
        assert "flow" in summary
        assert "persona" in summary

    def test_extractions_summarized(self):
        log = [
            {"type": "extraction", "value_type": "date"},
            {"type": "extraction", "value_type": "number"},
        ]
        summary = _summarize_spawn_log(log)
        assert "2 value extractions" in summary
        assert "date" in summary

    def test_llm_calls_summarized(self):
        log = [
            {"type": "llm_call", "provider": "anthropic", "latency_ms": 500},
            {"type": "llm_call", "provider": "anthropic", "latency_ms": 300},
        ]
        summary = _summarize_spawn_log(log)
        assert "2 LLM calls" in summary
        assert "800ms" in summary

    def test_mixed_types(self):
        log = [
            {"type": "secret_scan", "tool": "gitleaks"},
            {"type": "redaction", "pii_type": "email", "source": "s.md"},
            {"type": "classification", "label": "flow"},
            {"type": "extraction", "value_type": "date"},
            {"type": "llm_call", "provider": "openai", "latency_ms": 100},
        ]
        summary = _summarize_spawn_log(log)
        assert "1 secret detections" in summary
        assert "1 PII redaction" in summary
        assert "1 auto-classification" in summary
        assert "1 value extraction" in summary
        assert "1 LLM call" in summary

    def test_unknown_types_ignored(self):
        log = [{"type": "unknown_future_type", "data": "foo"}]
        summary = _summarize_spawn_log(log)
        assert summary == ""

    def test_summary_starts_with_header(self):
        log = [{"type": "redaction", "pii_type": "email", "source": "s.md"}]
        summary = _summarize_spawn_log(log)
        assert summary.startswith("Spawn-time pipeline activity:")
