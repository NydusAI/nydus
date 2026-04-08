"""Tests for ADD/SET/REMOVE directives and local egg inheritance (CR-001 Phase D)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
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
    Directive,
    InjectionMode,
    MemoryLabel,
    SecretKind,
)
from pynydus.engine.merger import load_base_egg, merge
from pynydus.engine.nydusfile import MergeOp, NydusfileError, parse

# ---------------------------------------------------------------------------
# Nydusfile parsing
# ---------------------------------------------------------------------------


class TestMergeDirectiveParsing:
    @pytest.mark.parametrize(
        ("snippet", "bucket", "value"),
        [
            ('ADD memory "Hello world"\n', Bucket.MEMORY, "Hello world"),
            ('ADD skill "./greet.md"\n', Bucket.SKILL, "./greet.md"),
            ("ADD secret API_KEY\n", Bucket.SECRET, "API_KEY"),
        ],
    )
    def test_parse_add_directives(self, snippet: str, bucket: Bucket, value: str) -> None:
        config = parse(f"FROM ./base.egg\n{snippet}")
        assert len(config.merge_ops) == 1
        op = config.merge_ops[0]
        assert op.action is Directive.ADD
        assert op.bucket is bucket
        assert op.value == value

    def test_parse_set_memory(self) -> None:
        config = parse('FROM ./base.egg\nSET memory.label=state "The sky is red"\n')
        assert len(config.merge_ops) == 1
        op = config.merge_ops[0]
        assert op.action is Directive.SET
        assert op.bucket is Bucket.MEMORY
        assert op.key == "label=state"
        assert op.value == "The sky is red"

    def test_parse_remove_skill(self) -> None:
        config = parse("FROM ./base.egg\nREMOVE skill old_skill\n")
        assert len(config.merge_ops) == 1
        op = config.merge_ops[0]
        assert op.action is Directive.REMOVE
        assert op.bucket is Bucket.SKILL
        assert op.key == "old_skill"

    def test_parse_remove_memory_by_selector(self) -> None:
        config = parse("FROM ./base.egg\nREMOVE memory.label=state\n")
        assert config.merge_ops[0].key == "label=state"

    def test_parse_multiple_ops(self) -> None:
        config = parse(
            "FROM ./base.egg\n"
            'ADD memory "new fact"\n'
            "REMOVE skill old_skill\n"
            'SET memory.label=flow "updated system"\n'
        )
        assert len(config.merge_ops) == 3

    def test_add_missing_args(self) -> None:
        with pytest.raises(NydusfileError, match="ADD requires"):
            parse("FROM ./base.egg\nADD memory\n")

    def test_set_missing_selector(self) -> None:
        with pytest.raises(NydusfileError, match="SET requires a selector"):
            parse('FROM ./base.egg\nSET memory "no selector"\n')

    def test_set_missing_value(self) -> None:
        with pytest.raises(NydusfileError, match="SET requires a value"):
            parse("FROM ./base.egg\nSET memory.label=state\n")

    def test_remove_missing_key(self) -> None:
        with pytest.raises(NydusfileError, match="REMOVE requires"):
            parse("FROM ./base.egg\nREMOVE memory\n")

    def test_unknown_bucket(self) -> None:
        with pytest.raises(NydusfileError, match="Unknown bucket"):
            parse('FROM ./base.egg\nADD tools "something"\n')

    def test_merge_ops_without_base_egg_raises(self) -> None:
        """Merge ops require FROM to point to a .egg file."""
        with pytest.raises(NydusfileError, match="require a base egg"):
            parse('SOURCE openclaw ./src\nADD memory "something"\n')


class TestFromBaseEgg:
    def test_from_egg_path(self) -> None:
        config = parse("FROM ./base.egg\n")
        assert config.base_egg == "./base.egg"

    def test_from_egg_absolute_path(self) -> None:
        config = parse("FROM /path/to/base.egg\n")
        assert config.base_egg == "/path/to/base.egg"

    def test_source_only_no_base_egg(self) -> None:
        config = parse("SOURCE openclaw ./src\n")
        assert config.base_egg is None


# ---------------------------------------------------------------------------
# Merger operations
# ---------------------------------------------------------------------------


def _make_base_egg() -> Egg:
    return Egg(
        manifest=Manifest(
            nydus_version="0.1.0",
            created_at=datetime.now(tz=timezone.utc),
            agent_type=AgentType.OPENCLAW,
            included_modules=[Bucket.SKILL, Bucket.MEMORY, Bucket.SECRET],
        ),
        skills=SkillsModule(
            skills=[
                SkillRecord(
                    id="skill_001",
                    name="greet",
                    agent_type="markdown_skill",
                    content="Say hello to the user",
                ),
            ]
        ),
        memory=MemoryModule(
            memory=[
                MemoryRecord(
                    id="mem_001",
                    text="I like cats",
                    label=MemoryLabel.PERSONA,
                    agent_type="openclaw",
                    source_store="SOUL.md",
                ),
                MemoryRecord(
                    id="mem_002",
                    text="The sky is blue",
                    label=MemoryLabel.STATE,
                    agent_type="openclaw",
                    source_store="MEMORY.md",
                ),
            ]
        ),
        secrets=SecretsModule(
            secrets=[
                SecretRecord(
                    id="secret_001",
                    placeholder="{{SECRET_001}}",
                    kind=SecretKind.CREDENTIAL,
                    name="API_KEY",
                    required_at_hatch=True,
                    injection_mode=InjectionMode.ENV,
                ),
            ]
        ),
    )


class TestMergerAdd:
    def test_add_memory(self) -> None:
        egg = _make_base_egg()
        ops = [MergeOp(action=Directive.ADD, bucket=Bucket.MEMORY, key="", value="New fact")]
        partial = merge(egg, ops)
        assert len(partial.memory.memory) == 3
        assert partial.memory.memory[-1].text == "New fact"

    def test_add_memory_with_label(self) -> None:
        egg = _make_base_egg()
        ops = [
            MergeOp(
                action=Directive.ADD, bucket=Bucket.MEMORY, key="label=flow", value="System prompt"
            )
        ]
        partial = merge(egg, ops)
        new_rec = partial.memory.memory[-1]
        assert new_rec.label == "flow"
        assert new_rec.text == "System prompt"

    def test_add_skill(self) -> None:
        egg = _make_base_egg()
        ops = [
            MergeOp(action=Directive.ADD, bucket=Bucket.SKILL, key="farewell", value="Say goodbye")
        ]
        partial = merge(egg, ops)
        assert len(partial.skills.skills) == 2
        assert partial.skills.skills[-1].name == "farewell"
        assert partial.skills.skills[-1].content == "Say goodbye"

    def test_add_secret(self) -> None:
        egg = _make_base_egg()
        ops = [MergeOp(action=Directive.ADD, bucket=Bucket.SECRET, key="", value="DB_PASSWORD")]
        partial = merge(egg, ops)
        assert len(partial.secrets.secrets) == 2
        assert partial.secrets.secrets[-1].name == "DB_PASSWORD"

    def test_add_memory_from_file(self, tmp_path: Path) -> None:
        content_file = tmp_path / "extra.md"
        content_file.write_text("Content from a file")
        egg = _make_base_egg()
        ops = [MergeOp(action=Directive.ADD, bucket=Bucket.MEMORY, key="", value=str(content_file))]
        partial = merge(egg, ops)
        assert partial.memory.memory[-1].text == "Content from a file"

    def test_add_memory_relative_path_resolves_from_base_dir(self, tmp_path: Path) -> None:
        (tmp_path / "notes.md").write_text("Resolved from base_dir")
        egg = _make_base_egg()
        ops = [MergeOp(action=Directive.ADD, bucket=Bucket.MEMORY, key="", value="./notes.md")]
        partial = merge(egg, ops, base_dir=tmp_path)
        assert partial.memory.memory[-1].text == "Resolved from base_dir"

    def test_relative_path_missing_file_raises(self, tmp_path: Path) -> None:
        egg = _make_base_egg()
        ops = [
            MergeOp(action=Directive.ADD, bucket=Bucket.MEMORY, key="", value="./nonexistent.md")
        ]
        with pytest.raises(NydusfileError, match="File not found"):
            merge(egg, ops, base_dir=tmp_path)

    def test_plain_text_value_returned_as_is(self) -> None:
        egg = _make_base_egg()
        ops = [MergeOp(action=Directive.ADD, bucket=Bucket.MEMORY, key="", value="Just plain text")]
        partial = merge(egg, ops)
        assert partial.memory.memory[-1].text == "Just plain text"


class TestMergerSet:
    def test_set_memory_by_label(self) -> None:
        egg = _make_base_egg()
        ops = [
            MergeOp(
                action=Directive.SET,
                bucket=Bucket.MEMORY,
                key="label=state",
                value="The sky is red",
            )
        ]
        partial = merge(egg, ops)
        fact_records = [r for r in partial.memory.memory if r.label == "state"]
        assert len(fact_records) == 1
        assert fact_records[0].text == "The sky is red"

    def test_set_skill_by_name(self) -> None:
        egg = _make_base_egg()
        ops = [
            MergeOp(
                action=Directive.SET,
                bucket=Bucket.SKILL,
                key="name=greet",
                value="Updated greeting",
            )
        ]
        partial = merge(egg, ops)
        assert partial.skills.skills[0].content == "Updated greeting"

    def test_set_nonexistent_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        egg = _make_base_egg()
        ops = [
            MergeOp(
                action=Directive.SET, bucket=Bucket.MEMORY, key="label=nonexistent", value="text"
            )
        ]
        with caplog.at_level("WARNING"):
            merge(egg, ops)
        assert any("no matching record" in r.message for r in caplog.records)


class TestMergerRemove:
    def test_remove_skill_by_name(self) -> None:
        egg = _make_base_egg()
        ops = [MergeOp(action=Directive.REMOVE, bucket=Bucket.SKILL, key="greet")]
        partial = merge(egg, ops)
        assert len(partial.skills.skills) == 0

    def test_remove_memory_by_label(self) -> None:
        egg = _make_base_egg()
        ops = [MergeOp(action=Directive.REMOVE, bucket=Bucket.MEMORY, key="label=state")]
        partial = merge(egg, ops)
        assert not any(r.label == "state" for r in partial.memory.memory)
        assert len(partial.memory.memory) == 1  # persona remains

    def test_remove_secret_by_name(self) -> None:
        egg = _make_base_egg()
        ops = [MergeOp(action=Directive.REMOVE, bucket=Bucket.SECRET, key="API_KEY")]
        partial = merge(egg, ops)
        assert len(partial.secrets.secrets) == 0

    def test_remove_memory_by_id(self) -> None:
        egg = _make_base_egg()
        ops = [MergeOp(action=Directive.REMOVE, bucket=Bucket.MEMORY, key="mem_001")]
        partial = merge(egg, ops)
        assert len(partial.memory.memory) == 1
        assert partial.memory.memory[0].id == "mem_002"


class TestLoadBaseEgg:
    def test_load_nonexistent_raises(self) -> None:
        from pynydus.api.errors import HatchError

        with pytest.raises(HatchError, match="not found"):
            load_base_egg("/nonexistent/path.egg")

    def test_load_and_merge_roundtrip(self, tmp_path: Path) -> None:
        """Pack an egg, load it as base, apply merge ops, verify result."""
        from pynydus.engine.packager import save

        egg = _make_base_egg()
        egg_path = tmp_path / "base.egg"
        save(egg, egg_path)

        loaded = load_base_egg(str(egg_path))
        ops = [
            MergeOp(action=Directive.ADD, bucket=Bucket.MEMORY, key="", value="New memory"),
            MergeOp(action=Directive.REMOVE, bucket=Bucket.SKILL, key="greet"),
        ]
        partial = merge(loaded, ops)
        assert len(partial.memory.memory) == 3  # 2 original + 1 added
        assert len(partial.skills.skills) == 0  # removed


# ---------------------------------------------------------------------------
# FROM + SOURCE integration
# ---------------------------------------------------------------------------


class TestFromPlusSource:
    """When both FROM and SOURCE are present, base egg records are merged with
    freshly extracted records from SOURCE paths."""

    def test_from_plus_source_merges_records(self, tmp_path: Path) -> None:
        from pynydus.engine.nydusfile import NydusfileConfig, SourceDirective
        from pynydus.engine.packager import save
        from pynydus.engine.pipeline import spawn

        base_egg = _make_base_egg()
        egg_path = tmp_path / "base.egg"
        save(base_egg, egg_path)

        source_dir = tmp_path / "agent"
        source_dir.mkdir()
        (source_dir / "SOUL.md").write_text("# Soul\nI love Python.")
        (source_dir / "MEMORY.md").write_text("# Knowledge\nPython is great.")

        config = NydusfileConfig(
            base_egg=str(egg_path),
            sources=[SourceDirective(agent_type="openclaw", path=str(source_dir))],
            redact=False,
        )
        egg, raw, logs = spawn(
            config,
            nydusfile_dir=tmp_path,
        )

        base_skill_names = {s.name for s in base_egg.skills.skills}
        result_skill_names = {s.name for s in egg.skills.skills}
        assert base_skill_names.issubset(result_skill_names)

        base_mem_texts = {m.text for m in base_egg.memory.memory}
        result_mem_texts = {m.text for m in egg.memory.memory}
        assert base_mem_texts.issubset(result_mem_texts)
        assert len(egg.memory.memory) > len(base_egg.memory.memory)

        ids = [s.id for s in egg.skills.skills]
        assert ids == sorted(ids)
        assert len(ids) == len(set(ids))

    def test_from_plus_source_with_merge_ops(self, tmp_path: Path) -> None:
        """ADD/SET/REMOVE modify the base egg before merging with SOURCE."""
        from pynydus.engine.nydusfile import (
            MergeOp,
            NydusfileConfig,
            SourceDirective,
        )
        from pynydus.engine.packager import save
        from pynydus.engine.pipeline import spawn

        base_egg = _make_base_egg()
        egg_path = tmp_path / "base.egg"
        save(base_egg, egg_path)

        source_dir = tmp_path / "agent"
        source_dir.mkdir()
        (source_dir / "SOUL.md").write_text("# Soul\nI love music.")

        config = NydusfileConfig(
            base_egg=str(egg_path),
            sources=[SourceDirective(agent_type="openclaw", path=str(source_dir))],
            merge_ops=[MergeOp(action=Directive.REMOVE, bucket=Bucket.SKILL, key="greet")],
            redact=False,
        )
        egg, raw, logs = spawn(
            config,
            nydusfile_dir=tmp_path,
        )

        skill_names = {s.name for s in egg.skills.skills}
        assert "greet" not in skill_names

        assert len(egg.memory.memory) > 0

    def test_from_only_still_works(self, tmp_path: Path) -> None:
        """FROM without SOURCE still returns the merged base egg directly."""
        from pynydus.engine.nydusfile import MergeOp, NydusfileConfig
        from pynydus.engine.packager import save
        from pynydus.engine.pipeline import spawn

        base_egg = _make_base_egg()
        egg_path = tmp_path / "base.egg"
        save(base_egg, egg_path)

        config = NydusfileConfig(
            base_egg=str(egg_path),
            merge_ops=[
                MergeOp(action=Directive.ADD, bucket=Bucket.MEMORY, key="", value="Extra"),
            ],
        )
        egg, raw, logs = spawn(
            config,
            nydusfile_dir=tmp_path,
        )

        assert len(egg.memory.memory) == 3  # 2 original + 1 added
        assert any(m.text == "Extra" for m in egg.memory.memory)
