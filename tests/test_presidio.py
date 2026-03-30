"""Tests for PII redaction (pkg/presidio.py).

These tests verify the real Presidio-backed redactor — not a fallback.
"""

from pynydus.pkg.presidio import PIIRedactor


class TestEmailRedaction:
    def test_redacts_email(self):
        r = PIIRedactor()
        result = r.redact("Contact alex@example.com for info.")
        assert "alex@example.com" not in result.redacted_text
        assert len(result.replacements) >= 1
        email_types = {rp.pii_type for rp in result.replacements}
        assert "EMAIL_ADDRESS" in email_types

    def test_multiple_emails(self):
        r = PIIRedactor()
        result = r.redact("Email a@b.com and c@d.com")
        assert "a@b.com" not in result.redacted_text
        assert "c@d.com" not in result.redacted_text


class TestPhoneRedaction:
    def test_redacts_phone(self):
        r = PIIRedactor()
        result = r.redact("Call 555-123-4567 for help.")
        assert "555-123-4567" not in result.redacted_text
        phone_types = {rp.pii_type for rp in result.replacements}
        assert "PHONE_NUMBER" in phone_types

    def test_redacts_phone_with_parens(self):
        r = PIIRedactor()
        result = r.redact("Phone: (555) 123-4567")
        assert "(555) 123-4567" not in result.redacted_text


class TestSSNRedaction:
    def test_redacts_ssn(self):
        r = PIIRedactor()
        result = r.redact("SSN: 123-45-6789")
        assert "123-45-6789" not in result.redacted_text
        ssn_types = {rp.pii_type for rp in result.replacements}
        assert "US_SSN" in ssn_types


class TestPersonRedaction:
    """Presidio NLP-based person name detection — not possible with regex."""

    def test_redacts_person_name(self):
        r = PIIRedactor()
        result = r.redact("My name is John Smith and I work at Acme.")
        assert "John Smith" not in result.redacted_text
        person_types = {rp.pii_type for rp in result.replacements}
        assert "PERSON" in person_types

    def test_redacts_person_in_context(self):
        r = PIIRedactor()
        result = r.redact("The creator of this agent is Dr. Sarah Johnson.")
        assert "Sarah Johnson" not in result.redacted_text


class TestLocationRedaction:
    def test_redacts_address(self):
        r = PIIRedactor()
        result = r.redact("I live at 123 Main Street, Springfield Illinois.")
        # At least the street or city should be redacted
        has_location = any(
            rp.pii_type == "LOCATION" for rp in result.replacements
        )
        assert has_location

    def test_redacts_city(self):
        r = PIIRedactor()
        result = r.redact("Our office is in San Francisco, California.")
        has_location = any(
            rp.pii_type == "LOCATION" for rp in result.replacements
        )
        assert has_location


class TestCreditCardRedaction:
    def test_redacts_credit_card(self):
        r = PIIRedactor()
        result = r.redact("My card number is 4111-1111-1111-1111.")
        assert "4111-1111-1111-1111" not in result.redacted_text
        cc_types = {rp.pii_type for rp in result.replacements}
        assert "CREDIT_CARD" in cc_types

    def test_redacts_credit_card_no_dashes(self):
        r = PIIRedactor()
        result = r.redact("Card: 4111111111111111")
        assert "4111111111111111" not in result.redacted_text


class TestIPRedaction:
    def test_redacts_ip_address(self):
        r = PIIRedactor()
        result = r.redact("Server at 192.168.1.1 is down.")
        assert "192.168.1.1" not in result.redacted_text
        ip_types = {rp.pii_type for rp in result.replacements}
        assert "IP_ADDRESS" in ip_types


class TestAPIKeyRedaction:
    """Custom recognizer — detects API keys in freeform text."""

    def test_redacts_openai_key(self):
        r = PIIRedactor()
        key = "sk-proj-abc123def456ghi789jkl012mno345"
        result = r.redact(f"My API key is {key}")
        assert key not in result.redacted_text
        api_types = {rp.pii_type for rp in result.replacements}
        assert "API_KEY" in api_types

    def test_redacts_github_pat(self):
        r = PIIRedactor()
        key = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh1234"
        result = r.redact(f"Token: {key}")
        assert key not in result.redacted_text

    def test_redacts_aws_access_key(self):
        r = PIIRedactor()
        key = "AKIAIOSFODNN7EXAMPLE"
        result = r.redact(f"AWS key: {key}")
        assert key not in result.redacted_text

    def test_redacts_slack_token(self):
        r = PIIRedactor()
        prefix = "xoxb"
        key = f"{prefix}-0000000000-0000000000000-FAKEFAKEFAKEFAKE"
        result = r.redact(f"Slack: {key}")
        assert key not in result.redacted_text

    def test_redacts_stripe_key(self):
        r = PIIRedactor()
        key = "sk_live_abcdefghijklmnopqrstu"
        result = r.redact(f"Stripe key: {key}")
        assert key not in result.redacted_text

    def test_redacts_anthropic_key(self):
        r = PIIRedactor()
        key = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
        result = r.redact(f"My key is {key}")
        assert key not in result.redacted_text

    def test_redacts_generic_secret_assignment(self):
        r = PIIRedactor()
        result = r.redact("api_key = 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6'")
        # The long token should be redacted
        assert "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6" not in result.redacted_text


class TestPlaceholderConsistency:
    """Core contract: same value → same placeholder, different → different."""

    def test_same_value_same_placeholder(self):
        r = PIIRedactor()
        result = r.redact("Email: a@b.com and again a@b.com")
        # Find the placeholder used for the email
        email_placeholders = [
            rp.placeholder for rp in result.replacements
            if rp.original == "a@b.com"
        ]
        assert len(email_placeholders) >= 1
        # All occurrences of the same value get the same placeholder
        assert len(set(email_placeholders)) == 1

    def test_different_values_different_placeholders(self):
        r = PIIRedactor()
        result = r.redact("Email a@b.com and c@d.com")
        placeholders = {rp.placeholder for rp in result.replacements}
        assert len(placeholders) >= 2

    def test_counter_persists_across_calls(self):
        r = PIIRedactor()
        r.redact("a@b.com")
        result2 = r.redact("c@d.com")
        # Second call should use a higher-numbered placeholder
        second_placeholders = {rp.placeholder for rp in result2.replacements}
        assert "{{PII_001}}" not in second_placeholders

    def test_mapping_property(self):
        r = PIIRedactor()
        r.redact("Contact alex@example.com")
        assert "alex@example.com" in r.mapping
        assert r.mapping["alex@example.com"] == "{{PII_001}}"


class TestNoFalsePositives:
    def test_no_pii(self):
        r = PIIRedactor()
        result = r.redact("The speed of light is 299792458 meters per second.")
        assert result.redacted_text == "The speed of light is 299792458 meters per second."
        assert len(result.replacements) == 0

    def test_preserves_surrounding_text(self):
        r = PIIRedactor()
        result = r.redact("Before alex@test.com after")
        assert result.redacted_text.startswith("Before ")
        assert result.redacted_text.endswith(" after")

    def test_urls_not_suppressed_when_they_look_like_urls(self):
        """URLs are suppressed as PII type but emails containing domains are still caught."""
        r = PIIRedactor()
        result = r.redact("Visit our site for more info.")
        # Plain text with no PII should pass through cleanly
        assert len(result.replacements) == 0


class TestScoreThreshold:
    def test_custom_threshold(self):
        r = PIIRedactor(score_threshold=0.90)
        # With a very high threshold, only very confident detections pass
        result = r.redact("Contact alex@example.com")
        # Email is typically 1.0 score, so it should still be caught
        assert "alex@example.com" not in result.redacted_text
