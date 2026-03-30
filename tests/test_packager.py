"""Tests for Egg packager (pack/unpack)."""

from pathlib import Path

import zipfile

import pytest

from pynydus.api.errors import EggError
from pynydus.api.schemas import Egg
from pynydus.engine.packager import (
    EMBEDDED_NYDUSFILE_NAME,
    pack_with_raw,
    read_logs,
    read_nydusfile,
    read_raw_artifacts,
    unpack,
)


class TestPackUnpack:
    def test_creates_egg_file(self, sample_egg: Egg, tmp_path: Path):
        path = pack_with_raw(sample_egg, tmp_path / "test.egg", {"soul.md": "hello"})
        assert path.exists()
        assert path.suffix == ".egg"

    def test_round_trip_manifest(self, sample_egg: Egg, tmp_path: Path):
        path = pack_with_raw(sample_egg, tmp_path / "test.egg", {})
        loaded = unpack(path)
        assert loaded.manifest.source_type == sample_egg.manifest.source_type
        assert loaded.manifest.nydus_version == sample_egg.manifest.nydus_version

    def test_round_trip_skills(self, sample_egg: Egg, tmp_path: Path):
        path = pack_with_raw(sample_egg, tmp_path / "test.egg", {})
        loaded = unpack(path)
        assert len(loaded.skills.skills) == 1
        assert loaded.skills.skills[0].name == "test"

    def test_round_trip_memory(self, sample_egg: Egg, tmp_path: Path):
        path = pack_with_raw(sample_egg, tmp_path / "test.egg", {})
        loaded = unpack(path)
        assert len(loaded.memory.memory) == 1

    def test_raw_artifacts(self, sample_egg: Egg, tmp_path: Path):
        raw = {"soul.md": "I am an agent.", "skill.md": "# Do stuff"}
        path = pack_with_raw(sample_egg, tmp_path / "test.egg", raw)
        artifacts = read_raw_artifacts(path)
        assert artifacts["soul.md"] == "I am an agent."
        assert artifacts["skill.md"] == "# Do stuff"

    def test_logs_present(self, sample_egg: Egg, tmp_path: Path):
        path = pack_with_raw(sample_egg, tmp_path / "test.egg", {})
        logs = read_logs(path)
        assert "spawn_log.json" in logs

    def test_unpack_missing_file(self, tmp_path: Path):
        with pytest.raises(EggError, match="not found"):
            unpack(tmp_path / "nonexistent.egg")

    def test_unpack_invalid_zip(self, tmp_path: Path):
        bad = tmp_path / "bad.egg"
        bad.write_text("not a zip")
        with pytest.raises(EggError, match="Invalid Egg"):
            unpack(bad)

    def test_pack_embeds_nydusfile_canonical_name(self, sample_egg: Egg, tmp_path: Path):
        nf = "SOURCE openclaw ./a\n"
        path = pack_with_raw(
            sample_egg, tmp_path / "with_nf.egg", {}, nydusfile_text=nf,
        )
        with zipfile.ZipFile(path, "r") as zf:
            assert EMBEDDED_NYDUSFILE_NAME in zf.namelist()
        assert read_nydusfile(path) == nf
