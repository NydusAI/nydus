"""Tests for PII redaction (``pynydus.security.presidio``)."""

from __future__ import annotations

import pytest
from pynydus.security.presidio import PIIRedactor


@pytest.mark.parametrize(
    ("sample", "forbidden", "must_include_type"),
    [
        ("Contact alex@example.com for info.", "alex@example.com", "EMAIL_ADDRESS"),
        ("Email a@b.com and c@d.com", "a@b.com", "EMAIL_ADDRESS"),
        ("Call 555-123-4567 for help.", "555-123-4567", "PHONE_NUMBER"),
        ("Phone: (555) 123-4567", "(555) 123-4567", "PHONE_NUMBER"),
        ("SSN: 123-45-6789", "123-45-6789", "US_SSN"),
        ("My name is John Smith and I work at Acme.", "John Smith", "PERSON"),
        ("I live at 123 Main Street, Springfield Illinois.", None, "LOCATION"),
        ("My card number is 4111-1111-1111-1111.", "4111-1111-1111-1111", "CREDIT_CARD"),
        ("Server at 192.168.1.1 is down.", "192.168.1.1", "IP_ADDRESS"),
    ],
)
def test_detects_pii(sample: str, forbidden: str | None, must_include_type: str):
    r = PIIRedactor()
    result = r.redact(sample)
    types = {rp.pii_type for rp in result.replacements}
    assert must_include_type in types
    if forbidden:
        assert forbidden not in result.redacted_text


def test_dedup_placeholder():
    r = PIIRedactor()
    result = r.redact("Email: a@b.com and again a@b.com")
    email_placeholders = [rp.placeholder for rp in result.replacements if rp.original == "a@b.com"]
    assert len(set(email_placeholders)) == 1


def test_no_false_positive():
    r = PIIRedactor()
    result = r.redact("The speed of light is 299792458 meters per second.")
    assert result.redacted_text == "The speed of light is 299792458 meters per second."
    assert len(result.replacements) == 0


def test_high_threshold():
    r = PIIRedactor(score_threshold=0.90)
    result = r.redact("Contact alex@example.com")
    assert "alex@example.com" not in result.redacted_text


def test_mixed_pii():
    r = PIIRedactor()
    result = r.redact("Call John Smith at 555-123-4567 or email john@example.com")
    types = {rp.pii_type for rp in result.replacements}
    assert "PERSON" in types
    assert "PHONE_NUMBER" in types
    assert "EMAIL_ADDRESS" in types


def test_pii_in_json():
    r = PIIRedactor()
    result = r.redact('{"email": "alice@example.com", "notes": "none"}')
    assert "alice@example.com" not in result.redacted_text


def test_pii_in_markdown():
    r = PIIRedactor()
    result = r.redact("[Contact](mailto:john@x.com)")
    assert "john@x.com" not in result.redacted_text


def test_counter_stability():
    r = PIIRedactor(start_index=1)
    r1 = r.redact("Email a@b.com")
    r2 = r.redact("Email c@d.com")
    p1 = {rp.placeholder for rp in r1.replacements}
    p2 = {rp.placeholder for rp in r2.replacements}
    assert p1.isdisjoint(p2)
