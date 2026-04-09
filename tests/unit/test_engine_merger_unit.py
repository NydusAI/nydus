"""Unit tests for base egg merge operations (engine/merger.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pynydus.api.errors import HatchError
from pynydus.common.enums import Bucket, Directive
from pynydus.engine.merger import load_base_egg, merge
from pynydus.engine.nydusfile import MergeOp

from conftest import make_egg


class TestLoadBaseEgg:
    def test_valid_egg(self, tmp_path: Path):
        from pynydus.engine.packager import save

        egg = make_egg()
        path = save(egg, tmp_path / "base.egg")
        loaded = load_base_egg(str(path))
        assert loaded.manifest.agent_type == egg.manifest.agent_type

    def test_missing_path_raises(self, tmp_path: Path):
        with pytest.raises(HatchError, match="Base egg not found"):
            load_base_egg(str(tmp_path / "nonexistent.egg"))


class TestMergeAdd:
    def test_add_memory(self):
        egg = make_egg()
        original_count = len(egg.memory.memory)
        ops = [
            MergeOp(
                action=Directive.ADD, bucket=Bucket.MEMORY, key="label=state", value="New fact."
            )
        ]
        partial = merge(egg, ops)
        assert len(partial.memory.memory) == original_count + 1
        assert partial.memory.memory[-1].text == "New fact."

    def test_add_skill(self):
        egg = make_egg()
        original_count = len(egg.skills.skills)
        ops = [MergeOp(action=Directive.ADD, bucket=Bucket.SKILL, key="new_skill", value="Do X.")]
        partial = merge(egg, ops)
        assert len(partial.skills.skills) == original_count + 1
        assert partial.skills.skills[-1].name == "new_skill"

    def test_add_secret(self):
        egg = make_egg()
        original_count = len(egg.secrets.secrets)
        ops = [
            MergeOp(
                action=Directive.ADD, bucket=Bucket.SECRET, key="NEW_API_KEY", value="NEW_API_KEY"
            )
        ]
        partial = merge(egg, ops)
        assert len(partial.secrets.secrets) == original_count + 1


class TestMergeSet:
    def test_set_replaces_memory_by_id(self):
        egg = make_egg()
        mem_id = egg.memory.memory[0].id
        ops = [
            MergeOp(
                action=Directive.SET, bucket=Bucket.MEMORY, key=f"id={mem_id}", value="Updated."
            )
        ]
        partial = merge(egg, ops)
        matched = [m for m in partial.memory.memory if m.id == mem_id]
        assert matched[0].text == "Updated."


class TestMergeRemove:
    def test_remove_by_id(self):
        egg = make_egg()
        mem_id = egg.memory.memory[0].id
        ops = [MergeOp(action=Directive.REMOVE, bucket=Bucket.MEMORY, key=mem_id)]
        partial = merge(egg, ops)
        assert not any(m.id == mem_id for m in partial.memory.memory)

    def test_remove_skill_by_name(self):
        egg = make_egg()
        skill_name = egg.skills.skills[0].name
        ops = [MergeOp(action=Directive.REMOVE, bucket=Bucket.SKILL, key=skill_name)]
        partial = merge(egg, ops)
        assert not any(s.name == skill_name for s in partial.skills.skills)


class TestMergeSequence:
    def test_multiple_ops_in_order(self):
        egg = make_egg()
        ops = [
            MergeOp(
                action=Directive.ADD, bucket=Bucket.MEMORY, key="label=state", value="Added fact."
            ),
            MergeOp(action=Directive.REMOVE, bucket=Bucket.SKILL, key=egg.skills.skills[0].name),
        ]
        partial = merge(egg, ops)
        assert any(m.text == "Added fact." for m in partial.memory.memory)
        assert len(partial.skills.skills) == 0
