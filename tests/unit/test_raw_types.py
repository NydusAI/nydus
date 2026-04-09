"""Tests for raw_types data models."""

from __future__ import annotations

from pynydus.api.raw_types import (
    ParseResult,
    RawMemory,
    RawSkill,
    RenderResult,
)
from pynydus.common.enums import MemoryLabel


class TestRawSkill:
    def test_minimal(self):
        s = RawSkill(name="greet", content="say hello")
        assert s.name == "greet"
        assert s.content == "say hello"
        assert s.source_file is None

    def test_with_source_file(self):
        s = RawSkill(name="greet", content="say hello", source_file="tools.py")
        assert s.source_file == "tools.py"


class TestRawMemory:
    def test_minimal(self):
        m = RawMemory(text="I like pizza")
        assert m.text == "I like pizza"
        assert m.source_file is None

    def test_with_source_file(self):
        m = RawMemory(text="I like pizza", source_file="memory.json")
        assert m.source_file == "memory.json"

    def test_with_label(self):
        m = RawMemory(text="I am helpful", label=MemoryLabel.PERSONA)
        assert m.label == MemoryLabel.PERSONA


class TestParseResult:
    def test_with_skills(self):
        r = ParseResult(
            skills=[RawSkill(name="a", content="body a")],
        )
        assert len(r.skills) == 1
        assert r.skills[0].name == "a"

    def test_with_memory(self):
        r = ParseResult(
            memory=[RawMemory(text="hello"), RawMemory(text="world")],
        )
        assert len(r.memory) == 2

    def test_with_mcp_configs(self):
        r = ParseResult(mcp_configs={"server1": {"command": "node"}})
        assert "server1" in r.mcp_configs

    def test_serialization_roundtrip(self):
        r = ParseResult(
            skills=[RawSkill(name="s", content="c")],
            source_metadata={"agent": "test"},
        )
        data = r.model_dump()
        r2 = ParseResult.model_validate(data)
        assert r == r2


class TestRenderResult:
    def test_with_files(self):
        r = RenderResult(files={"SOUL.md": "content"})
        assert r.files["SOUL.md"] == "content"

    def test_with_warnings(self):
        r = RenderResult(warnings=["something missing"])
        assert len(r.warnings) == 1
