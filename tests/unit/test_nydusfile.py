"""Tests for pynydus.engine.nydusfile — DSL parser and static verifier."""

from pathlib import Path

import pytest
from pynydus.api.errors import NydusfileError
from pynydus.common.enums import AgentType
from pynydus.engine.nydusfile import parse, resolve_nydusfile


class TestBasicParsing:
    def test_minimal(self):
        """SOURCE-only; omitted REDACT defaults to true."""
        cfg = parse("SOURCE openclaw ./src")
        assert cfg.redact is True

    def test_comments_and_blank_lines(self):
        text = """\
# This is a comment
SOURCE letta ./data

# Another comment
REDACT false
"""
        cfg = parse(text)
        assert cfg.redact is False

    def test_all_agent_types_via_source_directive(self):
        for src in AgentType:
            cfg = parse(f"SOURCE {src.value} ./data")
            assert len(cfg.sources) == 1
            assert cfg.sources[0].agent_type == src.value


class TestErrors:
    def test_missing_source_and_from(self):
        with pytest.raises(
            NydusfileError, match="at least one SOURCE directive or a FROM base egg"
        ):
            parse("REDACT true")

    def test_from_bare_agent_type_rejected(self):
        with pytest.raises(NydusfileError, match="FROM no longer accepts source types"):
            parse("FROM openclaw")

    def test_unknown_directive(self):
        with pytest.raises(NydusfileError, match="Unknown directive"):
            parse("SOURCE openclaw ./src\nBUILD fast")

    def test_unknown_redact_mode(self):
        with pytest.raises(NydusfileError, match="Invalid REDACT value"):
            parse("SOURCE openclaw ./src\nREDACT everything")

    def test_duplicate_from(self):
        with pytest.raises(NydusfileError, match="Duplicate directive FROM"):
            parse("FROM ./a.egg\nFROM ./b.egg")

    def test_duplicate_redact(self):
        with pytest.raises(NydusfileError, match="Duplicate directive REDACT"):
            parse("SOURCE openclaw ./src\nREDACT true\nREDACT false")

    def test_from_missing_arg(self):
        with pytest.raises(NydusfileError, match="FROM requires"):
            parse("FROM")

    def test_redact_missing_arg(self):
        with pytest.raises(NydusfileError, match="REDACT requires true or false"):
            parse("SOURCE openclaw ./src\nREDACT")

    def test_error_has_line_number(self):
        try:
            parse("SOURCE openclaw ./src\nBUILD fast")
        except NydusfileError as e:
            assert e.line == 2
            assert "line 2" in str(e)


class TestFromEggRef:
    """FROM now only accepts egg references, not bare source types."""

    def test_from_local_egg_path(self):
        cfg = parse("FROM ./base.egg")
        assert cfg.base_egg == "./base.egg"

    def test_from_versioned_egg_ref(self):
        cfg = parse("FROM nydus/openclaw:0.2.0\nSOURCE openclaw ./src")
        assert cfg.base_egg == "nydus/openclaw:0.2.0"

    def test_from_bare_agent_type_raises(self):
        with pytest.raises(NydusfileError, match="FROM no longer accepts source types"):
            parse("FROM openclaw")

    def test_from_bare_letta_raises(self):
        with pytest.raises(
            NydusfileError, match="FROM no longer accepts source types.*SOURCE letta"
        ):
            parse("FROM letta")

    def test_from_unknown_string_is_egg_ref(self):
        """Any string that is not a known source type is treated as an egg reference."""
        cfg = parse("FROM some_registry_egg")
        assert cfg.base_egg == "some_registry_egg"

    def test_source_only_no_from(self):
        """Nydusfile with only SOURCE (no FROM) parses successfully."""
        cfg = parse("SOURCE openclaw ./src")
        assert cfg.base_egg is None
        assert len(cfg.sources) == 1


# ---------------------------------------------------------------------------
# SOURCE directive (detailed)
# ---------------------------------------------------------------------------


class TestSourceDirective:
    def test_single_source(self):
        text = "SOURCE openclaw ./data"
        cfg = parse(text)
        assert len(cfg.sources) == 1
        assert cfg.sources[0].agent_type == "openclaw"
        assert cfg.sources[0].path == "./data"

    def test_second_source_rejected(self):
        text = "SOURCE openclaw ./oc_data\nSOURCE letta ./letta_data"
        with pytest.raises(NydusfileError, match="Only one SOURCE"):
            parse(text)

    def test_third_source_rejected(self):
        text = "SOURCE openclaw ./oc\nSOURCE letta ./lt\nSOURCE zeroclaw ./zc\n"
        with pytest.raises(NydusfileError, match="Only one SOURCE"):
            parse(text)

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
        with pytest.raises(NydusfileError, match="Unknown agent type"):
            parse(text)

    def test_agent_type_case_insensitive(self):
        text = "SOURCE OpenClaw ./data"
        cfg = parse(text)
        assert cfg.sources[0].agent_type == "openclaw"

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
        assert cfg.sources[0].agent_type == "zeroclaw"


# ---------------------------------------------------------------------------
# SOURCE combined scenarios
# ---------------------------------------------------------------------------


class TestSourceCombined:
    def test_full_nydusfile_with_sources(self):
        text = "SOURCE openclaw ./oc_proj\nREDACT true\n"
        cfg = parse(text)
        assert len(cfg.sources) == 1
        assert cfg.sources[0].agent_type == "openclaw"

    def test_source_with_merge_ops(self):
        text = 'FROM ./base.egg\nSOURCE letta ./letta_data\nADD memory "extra memory"\n'
        cfg = parse(text)
        assert len(cfg.sources) == 1
        assert len(cfg.merge_ops) == 1


# ---------------------------------------------------------------------------
# EXCLUDE, LABEL directives
# ---------------------------------------------------------------------------


class TestExcludeParsing:
    def test_single_label(self):
        from pynydus.common.enums import MemoryLabel

        cfg = parse("SOURCE openclaw ./src\nEXCLUDE state")
        assert cfg.excluded_memory_labels == [MemoryLabel.STATE]

    def test_multiple_labels(self):
        from pynydus.common.enums import MemoryLabel

        cfg = parse("SOURCE openclaw ./src\nEXCLUDE state\nEXCLUDE persona")
        assert cfg.excluded_memory_labels == [MemoryLabel.STATE, MemoryLabel.PERSONA]

    def test_label_token_case_insensitive(self):
        from pynydus.common.enums import MemoryLabel

        cfg = parse("SOURCE openclaw ./src\nEXCLUDE STATE\nEXCLUDE Persona")
        assert cfg.excluded_memory_labels == [MemoryLabel.STATE, MemoryLabel.PERSONA]

    def test_no_arg_raises(self):
        with pytest.raises(NydusfileError, match="memory label"):
            parse("SOURCE openclaw ./src\nEXCLUDE")

    def test_invalid_label_raises(self):
        with pytest.raises(NydusfileError, match="Unknown memory label"):
            parse("SOURCE openclaw ./src\nEXCLUDE not_a_bucket")

    def test_default_empty(self):
        cfg = parse("SOURCE openclaw ./src")
        assert cfg.excluded_memory_labels == []


class TestRemoveFileParsing:
    def test_remove_file_single_glob(self):
        cfg = parse("SOURCE openclaw ./src\nREMOVE file *.log")
        assert cfg.source_remove_globs == ["*.log"]
        assert not cfg.merge_ops

    def test_remove_file_multiple(self):
        cfg = parse("SOURCE openclaw ./src\nREMOVE file *.log\nREMOVE file temp_*")
        assert cfg.source_remove_globs == ["*.log", "temp_*"]

    def test_remove_file_requires_pattern(self):
        with pytest.raises(NydusfileError, match="glob pattern"):
            parse("SOURCE openclaw ./src\nREMOVE file")

    def test_remove_file_without_source_raises(self):
        with pytest.raises(NydusfileError, match="REMOVE file.*SOURCE"):
            parse("FROM ./base.egg\nREMOVE file *.log")

    def test_remove_skill_merge_op_not_file(self):
        from pynydus.common.enums import Bucket, Directive

        cfg = parse("FROM ./base.egg\nSOURCE openclaw ./src\nREMOVE skill foo")
        assert cfg.source_remove_globs == []
        assert len(cfg.merge_ops) == 1
        assert cfg.merge_ops[0].action is Directive.REMOVE
        assert cfg.merge_ops[0].bucket is Bucket.SKILL
        assert cfg.merge_ops[0].key == "foo"

    def test_remove_file_and_merge_together(self):
        from pynydus.common.enums import Bucket

        cfg = parse("FROM ./base.egg\nSOURCE openclaw ./src\nREMOVE file *.tmp\nREMOVE skill bar")
        assert cfg.source_remove_globs == ["*.tmp"]
        assert cfg.merge_ops[0].bucket is Bucket.SKILL
        assert cfg.merge_ops[0].key == "bar"


class TestLabelParsing:
    def test_single_label(self):
        cfg = parse("SOURCE openclaw ./src\nLABEL SOUL.md flow")
        assert cfg.custom_labels == {"SOUL.md": "flow"}

    def test_multiple_labels(self):
        cfg = parse("SOURCE openclaw ./src\nLABEL SOUL.md flow\nLABEL MEMORY.md state")
        assert cfg.custom_labels == {"SOUL.md": "flow", "MEMORY.md": "state"}

    def test_no_arg_raises(self):
        with pytest.raises(NydusfileError, match="requires"):
            parse("SOURCE openclaw ./src\nLABEL")

    def test_single_arg_raises(self):
        with pytest.raises(NydusfileError, match="two arguments"):
            parse("SOURCE openclaw ./src\nLABEL SOUL.md")

    def test_default_empty(self):
        cfg = parse("SOURCE openclaw ./src")
        assert cfg.custom_labels == {}

    def test_invalid_label_raises(self):
        with pytest.raises(NydusfileError, match="Unknown label"):
            parse("SOURCE openclaw ./src\nLABEL SOUL.md nonexistent_label")

    def test_duplicate_pattern_raises(self):
        with pytest.raises(NydusfileError, match="Duplicate LABEL"):
            parse("SOURCE openclaw ./src\nLABEL SOUL.md flow\nLABEL SOUL.md persona")


class TestFullNydusfileWithEnhancements:
    def test_all_directives(self):
        from pynydus.common.enums import MemoryLabel

        text = """\
SOURCE openclaw ./src
REDACT true
EXCLUDE context
EXCLUDE flow
LABEL SOUL.md flow
LABEL MEMORY.md state
"""
        cfg = parse(text)
        assert cfg.excluded_memory_labels == [MemoryLabel.CONTEXT, MemoryLabel.FLOW]
        assert cfg.custom_labels == {"SOUL.md": "flow", "MEMORY.md": "state"}


# ---------------------------------------------------------------------------
# resolve_nydusfile
# ---------------------------------------------------------------------------


class TestResolveNydusfile:
    def test_existing_nydusfile_returned(self, tmp_path: Path):
        nf = tmp_path / "Nydusfile"
        nf.write_text("SOURCE openclaw ./\n")
        result = resolve_nydusfile(tmp_path)
        assert result == nf

    def test_generates_default_for_openclaw(self, tmp_path: Path):
        # SKILL.md matches OpenClaw only; SOUL.md would also match ZeroClaw (shared persona files).
        (tmp_path / "SKILL.md").write_text("hello")
        result = resolve_nydusfile(tmp_path)
        assert result.exists()
        cfg = parse(result.read_text())
        assert cfg.sources[0].agent_type == "openclaw"

    def test_generates_default_for_letta(self, tmp_path: Path):
        import json

        (tmp_path / "agent_state.json").write_text(json.dumps({"system": "hi"}))
        result = resolve_nydusfile(tmp_path)
        assert result.exists()
        cfg = parse(result.read_text())
        assert cfg.sources[0].agent_type == "letta"

    def test_ambiguous_layout_raises(self, tmp_path: Path):
        """SOUL.md + AGENTS.md match both OpenClaw and ZeroClaw heuristics."""
        (tmp_path / "SOUL.md").write_text("x")
        (tmp_path / "AGENTS.md").write_text("y")
        with pytest.raises(NydusfileError, match="Ambiguous agent layout"):
            resolve_nydusfile(tmp_path)

    def test_unknown_dir_raises(self, tmp_path: Path):
        with pytest.raises(NydusfileError, match="Cannot auto-detect"):
            resolve_nydusfile(tmp_path)
