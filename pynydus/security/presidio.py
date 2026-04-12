"""PII redaction using Microsoft Presidio + custom recognizers.

Presidio handles **PII only**: names, emails, phone numbers, SSNs, credit
cards, addresses, etc.  Secret/credential detection is handled by gitleaks
(see ``pynydus.security.gitleaks``).

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
# Custom recognizers: PII patterns Presidio doesn't cover out of the box
# ---------------------------------------------------------------------------


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
    """Create a Presidio AnalyzerEngine with PII-focused custom recognizers."""
    analyzer = AnalyzerEngine()

    analyzer.registry.add_recognizer(_build_ssn_recognizer())
    analyzer.registry.add_recognizer(_build_us_passport_recognizer())
    analyzer.registry.add_recognizer(_build_drivers_license_recognizer())

    return analyzer


# Singleton: AnalyzerEngine is expensive to create (loads NLP model).
_analyzer: AnalyzerEngine | None = None


def _get_analyzer() -> AnalyzerEngine:
    """Return the singleton AnalyzerEngine, creating it on first call."""
    global _analyzer
    if _analyzer is None:
        _analyzer = _create_analyzer()
    return _analyzer


# ---------------------------------------------------------------------------
# Public API: same interface as before, now backed by Presidio
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
    """Stateful PII redactor with stable ``{{PII_NNN}}`` placeholders.

    Uses Microsoft Presidio plus custom recognizers. The same surface value
    maps to the same placeholder across calls on one instance.
    """

    def __init__(
        self,
        start_index: int = 1,
        score_threshold: float = _DEFAULT_SCORE_THRESHOLD,
    ):
        """Create a redactor.

        Args:
            start_index: First placeholder index (default ``1`` → ``{{PII_001}}``).
            score_threshold: Minimum Presidio confidence to accept a span.
        """
        self._counter = start_index
        self._seen: dict[str, str] = {}  # original value → placeholder
        self._score_threshold = score_threshold

    def redact(self, text: str) -> RedactionResult:
        """Redact PII spans. repeated values reuse the same placeholder.

        Args:
            text: Input UTF-8 text.

        Returns:
            Redacted text and per-span replacement metadata.
        """
        analyzer = _get_analyzer()
        raw_results: list[RecognizerResult] = analyzer.analyze(
            text=text,
            language="en",
            score_threshold=self._score_threshold,
        )

        results = [r for r in raw_results if r.entity_type not in _SUPPRESSED_ENTITIES]
        results = _resolve_overlaps(results)

        if not results:
            return RedactionResult(redacted_text=text, replacements=[])

        results.sort(key=lambda r: r.start)

        replacements: list[PIIReplacement] = []
        redacted = text

        # Reverse order so earlier spans' positions aren't shifted by later replacements
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

        replacements.reverse()
        return RedactionResult(redacted_text=redacted, replacements=replacements)

    def _get_placeholder(self, value: str) -> str:
        """Return existing or allocate next ``{{PII_NNN}}`` for *value*."""
        if value not in self._seen:
            self._seen[value] = f"{{{{PII_{self._counter:03d}}}}}"
            self._counter += 1
        return self._seen[value]

    @property
    def counter(self) -> int:
        """Next placeholder index after the last assignment."""
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
