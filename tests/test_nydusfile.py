"""Tests for pynydus.engine.nydusfile — DSL parser and static verifier."""

import pytest

from pynydus.api.errors import NydusfileError
from pynydus.api.schemas import Bucket, PriorityHint, RedactMode, SourceType
from pynydus.engine.nydusfile import SourceDirective, parse


class TestBasicParsing:
    def test_minimal(self):
        cfg = parse("SOURCE openclaw ./src")
        assert cfg.source == SourceType.OPENCLAW
        assert cfg.redact == RedactMode.PII  # default
        assert cfg.include is None
        assert cfg.exclude is None
        assert cfg.purpose is None

    def test_full_example(self):
        text = """\
SOURCE openclaw ./src
INCLUDE skills, memory
EXCLUDE secrets
REDACT pii
PRIORITIZE recent_history
PRIORITIZE compact_memory
PURPOSE "portable research assistant"
"""
        cfg = parse(text)
        assert cfg.source == SourceType.OPENCLAW
        assert cfg.include == {Bucket.SKILLS, Bucket.MEMORY}
        assert cfg.exclude == {Bucket.SECRETS}
        assert cfg.redact == RedactMode.PII
        assert cfg.priorities == [PriorityHint.RECENT_HISTORY, PriorityHint.COMPACT_MEMORY]
        assert cfg.purpose == "portable research assistant"

    def test_comments_and_blank_lines(self):
        text = """\
# This is a comment
SOURCE letta ./data

# Another comment
REDACT all
"""
        cfg = parse(text)
        assert cfg.source == SourceType.LETTA
        assert cfg.redact == RedactMode.ALL

    def test_all_source_types_via_source_directive(self):
        for src in SourceType:
            cfg = parse(f"SOURCE {src.value} ./data")
            assert cfg.source == src


class TestEffectiveBuckets:
    def test_all_by_default(self):
        cfg = parse("SOURCE openclaw ./src")
        assert cfg.effective_buckets == set(Bucket)

    def test_include_subset(self):
        cfg = parse("SOURCE openclaw ./src\nINCLUDE skills, memory")
        assert cfg.effective_buckets == {Bucket.SKILLS, Bucket.MEMORY}

    def test_exclude_removes(self):
        cfg = parse("SOURCE openclaw ./src\nEXCLUDE secrets")
        assert cfg.effective_buckets == {Bucket.SKILLS, Bucket.MEMORY}

    def test_include_and_exclude_no_overlap(self):
        cfg = parse("SOURCE openclaw ./src\nINCLUDE skills, memory\nEXCLUDE secrets")
        assert cfg.effective_buckets == {Bucket.SKILLS, Bucket.MEMORY}


class TestErrors:
    def test_missing_source_and_from(self):
        with pytest.raises(NydusfileError, match="at least one SOURCE directive or a FROM base egg"):
            parse("REDACT pii")

    def test_from_bare_source_type_rejected(self):
        with pytest.raises(NydusfileError, match="FROM no longer accepts source types"):
            parse("FROM openclaw")

    def test_from_invalid_egg_ref(self):
        with pytest.raises(NydusfileError, match="Invalid egg reference"):
            parse("FROM unknown_platform")

    def test_unknown_directive(self):
        with pytest.raises(NydusfileError, match="Unknown directive"):
            parse("SOURCE openclaw ./src\nBUILD fast")

    def test_unknown_bucket(self):
        with pytest.raises(NydusfileError, match="Unknown bucket"):
            parse("SOURCE openclaw ./src\nINCLUDE skills, tools")

    def test_unknown_redact_mode(self):
        with pytest.raises(NydusfileError, match="Unknown redaction mode"):
            parse("SOURCE openclaw ./src\nREDACT everything")

    def test_unknown_priority(self):
        with pytest.raises(NydusfileError, match="Unknown priority hint"):
            parse("SOURCE openclaw ./src\nPRIORITIZE speed")

    def test_duplicate_from(self):
        with pytest.raises(NydusfileError, match="Duplicate directive FROM"):
            parse("FROM ./a.egg\nFROM ./b.egg")

    def test_duplicate_redact(self):
        with pytest.raises(NydusfileError, match="Duplicate directive REDACT"):
            parse("SOURCE openclaw ./src\nREDACT pii\nREDACT all")

    def test_contradiction(self):
        with pytest.raises(NydusfileError, match="Contradictory include/exclude"):
            parse("SOURCE openclaw ./src\nINCLUDE skills\nEXCLUDE skills")

    def test_purpose_unquoted(self):
        with pytest.raises(NydusfileError, match="quoted string"):
            parse('SOURCE openclaw ./src\nPURPOSE research assistant')

    def test_from_missing_arg(self):
        with pytest.raises(NydusfileError, match="FROM requires"):
            parse("FROM")

    def test_redact_missing_arg(self):
        with pytest.raises(NydusfileError, match="REDACT requires"):
            parse("SOURCE openclaw ./src\nREDACT")

    def test_error_has_line_number(self):
        try:
            parse("SOURCE openclaw ./src\nBUILD fast")
        except NydusfileError as e:
            assert e.line == 2
            assert "line 2" in str(e)


class TestMultiplePrioritize:
    def test_allowed(self):
        text = """\
SOURCE openclaw ./src
PRIORITIZE recent_history
PRIORITIZE skills
PRIORITIZE compact_memory
"""
        cfg = parse(text)
        assert len(cfg.priorities) == 3


class TestFromEggRef:
    """FROM now only accepts egg references, not bare source types."""

    def test_from_local_egg_path(self):
        cfg = parse("FROM ./base.egg")
        assert cfg.base_egg == "./base.egg"

    def test_from_versioned_egg_ref(self):
        cfg = parse("FROM nydus/openclaw:0.2.0\nSOURCE openclaw ./src")
        assert cfg.base_egg == "nydus/openclaw:0.2.0"

    def test_from_bare_source_type_raises(self):
        with pytest.raises(NydusfileError, match="FROM no longer accepts source types"):
            parse("FROM openclaw")

    def test_from_bare_letta_raises(self):
        with pytest.raises(NydusfileError, match="FROM no longer accepts source types.*SOURCE letta"):
            parse("FROM letta")

    def test_source_only_no_from(self):
        """Nydusfile with only SOURCE (no FROM) parses successfully."""
        cfg = parse("SOURCE openclaw ./src")
        assert cfg.base_egg is None
        assert cfg.source == SourceType.OPENCLAW
        assert len(cfg.sources) == 1


# ---------------------------------------------------------------------------
# SOURCE directive (detailed)
# ---------------------------------------------------------------------------


class TestSourceDirective:
    def test_single_source(self):
        text = "SOURCE openclaw ./data"
        cfg = parse(text)
        assert len(cfg.sources) == 1
        assert cfg.sources[0].source_type == "openclaw"
        assert cfg.sources[0].path == "./data"

    def test_multiple_sources(self):
        text = "SOURCE openclaw ./oc_data\nSOURCE letta ./letta_data"
        cfg = parse(text)
        assert len(cfg.sources) == 2
        assert cfg.sources[0].source_type == "openclaw"
        assert cfg.sources[1].source_type == "letta"

    def test_three_sources(self):
        text = (
            "SOURCE openclaw ./oc\n"
            "SOURCE letta ./lt\n"
            "SOURCE zeroclaw ./zc\n"
        )
        cfg = parse(text)
        assert len(cfg.sources) == 3

    def test_target_directive_rejected_before_source(self):
        """TARGET is not part of the Nydusfile DSL (unknown directive)."""
        text = "SOURCE openclaw ./data\nTARGET letta"
        with pytest.raises(NydusfileError, match="Unknown directive"):
            parse(text)

    def test_source_missing_arg_raises(self):
        text = "SOURCE openclaw ./data\nSOURCE"
        with pytest.raises(NydusfileError, match="SOURCE requires"):
            parse(text)

    def test_source_missing_path_raises(self):
        text = "SOURCE openclaw ./data\nSOURCE letta"
        with pytest.raises(NydusfileError, match="SOURCE requires two"):
            parse(text)

    def test_source_invalid_type_raises(self):
        text = "SOURCE unknown_type ./data"
        with pytest.raises(NydusfileError, match="Unknown source type"):
            parse(text)

    def test_duplicate_source_raises(self):
        text = "SOURCE openclaw ./data\nSOURCE openclaw ./data"
        with pytest.raises(NydusfileError, match="Duplicate SOURCE"):
            parse(text)

    def test_same_type_different_path_ok(self):
        text = "SOURCE openclaw ./data1\nSOURCE openclaw ./data2"
        cfg = parse(text)
        assert len(cfg.sources) == 2

    def test_source_type_case_insensitive(self):
        text = "SOURCE OpenClaw ./data"
        cfg = parse(text)
        assert cfg.sources[0].source_type == "openclaw"

    def test_from_base_egg_no_sources(self):
        text = "FROM ./base.egg"
        cfg = parse(text)
        assert cfg.sources == []
        assert cfg.base_egg == "./base.egg"

    def test_source_with_space_in_path(self):
        text = "SOURCE openclaw ./my data folder"
        cfg = parse(text)
        assert cfg.sources[0].path == "./my data folder"

    def test_source_zeroclaw(self):
        text = "SOURCE zeroclaw ./zc_data"
        cfg = parse(text)
        assert cfg.sources[0].source_type == "zeroclaw"

    def test_source_directive_dataclass(self):
        sd = SourceDirective(source_type="openclaw", path="./data")
        assert sd.source_type == "openclaw"
        assert sd.path == "./data"


# ---------------------------------------------------------------------------
# SOURCE combined scenarios
# ---------------------------------------------------------------------------


class TestSourceCombined:
    def test_full_nydusfile_with_sources(self):
        text = (
            "SOURCE openclaw ./oc_proj\n"
            "SOURCE letta ./letta_proj\n"
            "REDACT all\n"
            'PURPOSE "Multi-source migration"\n'
        )
        cfg = parse(text)
        assert cfg.source.value == "openclaw"
        assert len(cfg.sources) == 2
        assert cfg.purpose == "Multi-source migration"

    def test_source_with_merge_ops(self):
        text = (
            "FROM ./base.egg\n"
            "SOURCE letta ./letta_data\n"
            'ADD memory "extra memory"\n'
        )
        cfg = parse(text)
        assert len(cfg.sources) == 1
        assert len(cfg.merge_ops) == 1
