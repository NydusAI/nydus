"""PII and secret redaction using Microsoft Presidio + custom recognizers.

Uses Presidio's NLP-backed analyzer for entity detection (persons, locations,
credit cards, etc.) and adds custom recognizers for API keys, SSNs, and other
patterns that Presidio does not cover out of the box.

Required dependencies:
  - presidio-analyzer >= 2.2
  - presidio-anonymizer >= 2.2
  - spaCy model: en_core_web_lg
"""

from __future__ import annotations

from dataclasses import dataclass, field

from presidio_analyzer import (
    AnalyzerEngine,
    Pattern,
    PatternRecognizer,
    RecognizerResult,
)

# ---------------------------------------------------------------------------
# Custom recognizers — patterns Presidio doesn't cover
# ---------------------------------------------------------------------------


def _build_api_key_recognizer() -> PatternRecognizer:
    """Detect common API key formats in freeform text."""
    return PatternRecognizer(
        supported_entity="API_KEY",
        name="ApiKeyRecognizer",
        patterns=[
            # OpenAI: sk-... (at least 20 chars)
            Pattern("openai_key", r"\bsk-[A-Za-z0-9_-]{20,}\b", 0.95),
            # OpenAI project key: sk-proj-...
            Pattern("openai_proj_key", r"\bsk-proj-[A-Za-z0-9_-]{20,}\b", 0.95),
            # Anthropic: sk-ant-...
            Pattern("anthropic_key", r"\bsk-ant-[A-Za-z0-9_-]{20,}\b", 0.95),
            # GitHub personal access token: ghp_...
            Pattern("github_pat", r"\bghp_[A-Za-z0-9]{36,}\b", 0.95),
            # GitHub fine-grained token: github_pat_...
            Pattern("github_fine", r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", 0.95),
            # AWS access key: AKIA...
            Pattern("aws_access", r"\bAKIA[0-9A-Z]{16}\b", 0.95),
            # AWS secret key (40 hex-ish chars after a separator)
            Pattern(
                "aws_secret",
                r"(?:aws_secret_access_key|secret_key)\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?",
                0.90,
            ),
            # Slack bot/user tokens: xoxb- / xoxp-
            Pattern("slack_token", r"\bxox[bp]-[A-Za-z0-9-]{24,}\b", 0.95),
            # Google API key: AIza...
            Pattern("google_api", r"\bAIza[A-Za-z0-9_-]{35}\b", 0.95),
            # Stripe: sk_live_ / sk_test_ / pk_live_ / pk_test_
            Pattern("stripe_key", r"\b[sp]k_(live|test)_[A-Za-z0-9]{20,}\b", 0.95),
            # Generic long hex/base64 secrets (32+ chars after key-like label)
            Pattern(
                "generic_secret_assignment",
                r"(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|bearer)"
                r"\s*[:=]\s*['\"]?([A-Za-z0-9_/+=-]{32,})['\"]?",
                0.80,
            ),
        ],
        supported_language="en",
        context=[
            "key", "token", "secret", "api", "credential", "auth",
            "bearer", "password", "access",
        ],
    )


def _build_ssn_recognizer() -> PatternRecognizer:
    """Detect US Social Security Numbers (Presidio's built-in sometimes misses)."""
    return PatternRecognizer(
        supported_entity="US_SSN",
        name="CustomSSNRecognizer",
        patterns=[
            Pattern("ssn_dashed", r"\b\d{3}-\d{2}-\d{4}\b", 0.85),
            Pattern("ssn_spaced", r"\b\d{3}\s\d{2}\s\d{4}\b", 0.80),
        ],
        supported_language="en",
        context=["ssn", "social security", "social_security"],
    )


def _build_us_passport_recognizer() -> PatternRecognizer:
    """Detect US passport numbers."""
    return PatternRecognizer(
        supported_entity="US_PASSPORT",
        name="USPassportRecognizer",
        patterns=[
            Pattern("us_passport", r"\b[A-Z]\d{8}\b", 0.40),
        ],
        supported_language="en",
        context=["passport", "travel document"],
    )


def _build_drivers_license_recognizer() -> PatternRecognizer:
    """Detect common US driver's license patterns."""
    return PatternRecognizer(
        supported_entity="US_DRIVERS_LICENSE",
        name="DriversLicenseRecognizer",
        patterns=[
            # Generic: 1 letter + 6-14 digits (covers many US states)
            Pattern("dl_generic", r"\b[A-Z]\d{6,14}\b", 0.30),
        ],
        supported_language="en",
        context=["driver", "license", "licence", "dl", "driving"],
    )


# ---------------------------------------------------------------------------
# Analyzer factory
# ---------------------------------------------------------------------------


def _create_analyzer() -> AnalyzerEngine:
    """Create a Presidio AnalyzerEngine with all custom recognizers."""
    analyzer = AnalyzerEngine()

    # Register custom recognizers
    analyzer.registry.add_recognizer(_build_api_key_recognizer())
    analyzer.registry.add_recognizer(_build_ssn_recognizer())
    analyzer.registry.add_recognizer(_build_us_passport_recognizer())
    analyzer.registry.add_recognizer(_build_drivers_license_recognizer())

    return analyzer


# Singleton — AnalyzerEngine is expensive to create (loads NLP model).
_analyzer: AnalyzerEngine | None = None


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        _analyzer = _create_analyzer()
    return _analyzer


# ---------------------------------------------------------------------------
# Public API — same interface as before, now backed by Presidio
# ---------------------------------------------------------------------------

# Minimum confidence score for a detection to be included.
_DEFAULT_SCORE_THRESHOLD = 0.40

# Entity types we always suppress (too noisy / not real PII).
_SUPPRESSED_ENTITIES = {"URL", "DATE_TIME", "NRP"}


@dataclass
class PIIReplacement:
    """A single PII replacement."""

    original: str
    pii_type: str
    placeholder: str
    start: int
    end: int


@dataclass
class RedactionResult:
    """Result of PII redaction on a text."""

    redacted_text: str
    replacements: list[PIIReplacement] = field(default_factory=list)


class PIIRedactor:
    """Stateful PII redactor that maintains a consistent placeholder mapping.

    Uses Microsoft Presidio for entity detection and adds custom recognizers
    for API keys, SSNs, and other patterns. Maintains stable placeholders
    so the same PII value always maps to the same ``{{PII_NNN}}`` token
    across multiple calls.
    """

    def __init__(
        self,
        start_index: int = 1,
        score_threshold: float = _DEFAULT_SCORE_THRESHOLD,
    ):
        self._counter = start_index
        self._seen: dict[str, str] = {}  # original value → placeholder
        self._score_threshold = score_threshold

    def redact(self, text: str) -> RedactionResult:
        """Redact PII from text. Same values always get the same placeholder."""
        analyzer = _get_analyzer()
        raw_results: list[RecognizerResult] = analyzer.analyze(
            text=text,
            language="en",
            score_threshold=self._score_threshold,
        )

        # Filter suppressed entity types
        results = [
            r for r in raw_results if r.entity_type not in _SUPPRESSED_ENTITIES
        ]

        # Resolve overlaps: keep the higher-scoring / longer match
        results = _resolve_overlaps(results)

        if not results:
            return RedactionResult(redacted_text=text, replacements=[])

        # Sort ascending by position for result ordering
        results.sort(key=lambda r: r.start)

        replacements: list[PIIReplacement] = []
        redacted = text

        # Replace in reverse order to preserve positions
        for r in reversed(results):
            original = text[r.start : r.end]
            placeholder = self._get_placeholder(original)
            redacted = redacted[: r.start] + placeholder + redacted[r.end :]
            replacements.append(
                PIIReplacement(
                    original=original,
                    pii_type=r.entity_type,
                    placeholder=placeholder,
                    start=r.start,
                    end=r.end,
                )
            )

        # Return replacements in document order
        replacements.reverse()
        return RedactionResult(redacted_text=redacted, replacements=replacements)

    def _get_placeholder(self, value: str) -> str:
        """Get or create a placeholder for a value."""
        if value not in self._seen:
            self._seen[value] = f"{{{{PII_{self._counter:03d}}}}}"
            self._counter += 1
        return self._seen[value]

    def redact_batch(
        self, items: list[tuple[str, str]]
    ) -> list[tuple[RedactionResult, str]]:
        """Redact PII across multiple text items at once.

        Parameters
        ----------
        items:
            List of ``(text, back_ref)`` tuples.  ``back_ref`` is an opaque
            string that lets the caller trace each result back to its origin
            (e.g. ``"skill:skill_001"``).

        Returns
        -------
        list[tuple[RedactionResult, str]]
            One ``(RedactionResult, back_ref)`` per input item.
        """
        return [(self.redact(text), ref) for text, ref in items]

    @property
    def counter(self) -> int:
        return self._counter

    @property
    def mapping(self) -> dict[str, str]:
        """Return the original → placeholder mapping."""
        return dict(self._seen)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_overlaps(results: list[RecognizerResult]) -> list[RecognizerResult]:
    """Remove overlapping detections, keeping the highest-scoring / longest."""
    if not results:
        return []

    # Sort by score descending, then by length descending
    ranked = sorted(results, key=lambda r: (-r.score, -(r.end - r.start)))
    accepted: list[RecognizerResult] = []
    taken_positions: set[int] = set()

    for r in ranked:
        span = set(range(r.start, r.end))
        if span & taken_positions:
            continue
        accepted.append(r)
        taken_positions |= span

    return accepted
