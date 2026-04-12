"""``.egg`` ZIP layout: save/load round-trip, raw/, spawn_log, signing hooks."""

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pynydus.api.errors import EggError
from pynydus.api.schemas import Egg
from pynydus.engine.packager import (
    EMBEDDED_NYDUSFILE_NAME,
    load,
    read_logs,
    read_nydusfile,
    read_raw_artifacts,
    save,
)


class TestPackUnpack:
    def test_creates_egg_file(self, sample_egg: Egg, tmp_path: Path):
        path = save(sample_egg, tmp_path / "test.egg", raw_artifacts={"SOUL.md": "hello"})
        assert path.exists()
        assert path.suffix == ".egg"

    def test_round_trip_manifest(self, sample_egg: Egg, tmp_path: Path):
        path = save(sample_egg, tmp_path / "test.egg")
        loaded = load(path)
        assert loaded.manifest.agent_type == sample_egg.manifest.agent_type
        assert loaded.manifest.nydus_version == sample_egg.manifest.nydus_version

    def test_round_trip_skills(self, sample_egg: Egg, tmp_path: Path):
        path = save(sample_egg, tmp_path / "test.egg")
        loaded = load(path)
        assert len(loaded.skills.skills) == 1
        assert loaded.skills.skills[0].name == "test"

    def test_round_trip_memory(self, sample_egg: Egg, tmp_path: Path):
        path = save(sample_egg, tmp_path / "test.egg")
        loaded = load(path)
        assert len(loaded.memory.memory) == 1

    def test_save_load_roundtrip_raw_and_log(self, sample_egg: Egg, tmp_path: Path):
        raw = {"SOUL.md": "I am an agent.", "SKILL.md": "# Do stuff"}
        log = [{"type": "test", "ok": True}]
        path = save(
            sample_egg,
            tmp_path / "full.egg",
            raw_artifacts=raw,
            spawn_log=log,
            nydusfile_text="SOURCE openclaw ./x\n",
        )
        loaded = load(path)
        assert loaded.raw_artifacts == raw
        assert loaded.spawn_log == log
        assert loaded.nydusfile == "SOURCE openclaw ./x\n"

    def test_raw_artifacts(self, sample_egg: Egg, tmp_path: Path):
        raw = {"SOUL.md": "I am an agent.", "SKILL.md": "# Do stuff"}
        path = save(sample_egg, tmp_path / "test.egg", raw_artifacts=raw)
        artifacts = read_raw_artifacts(path)
        assert artifacts["SOUL.md"] == "I am an agent."
        assert artifacts["SKILL.md"] == "# Do stuff"

    def test_logs_present(self, sample_egg: Egg, tmp_path: Path):
        path = save(sample_egg, tmp_path / "test.egg")
        logs = read_logs(path)
        assert "spawn_log.json" in logs

    def test_load_missing_file(self, tmp_path: Path):
        with pytest.raises(EggError, match="not found"):
            load(tmp_path / "nonexistent.egg")

    def test_load_invalid_zip(self, tmp_path: Path):
        bad = tmp_path / "bad.egg"
        bad.write_text("not a zip")
        with pytest.raises(EggError, match="Invalid Egg"):
            load(bad)

    def test_save_embeds_nydusfile_canonical_name(self, sample_egg: Egg, tmp_path: Path):
        nf = "SOURCE openclaw ./a\n"
        path = save(sample_egg, tmp_path / "with_nf.egg", nydusfile_text=nf)
        with zipfile.ZipFile(path, "r") as zf:
            assert EMBEDDED_NYDUSFILE_NAME in zf.namelist()
        assert read_nydusfile(path) == nf

    def test_load_include_raw_false_skips_raw(self, sample_egg: Egg, tmp_path: Path):
        raw = {"SOUL.md": "body"}
        path = save(sample_egg, tmp_path / "with_raw.egg", raw_artifacts=raw)
        full = load(path)
        assert full.raw_artifacts == raw
        lite = load(path, include_raw=False)
        assert lite.raw_artifacts == {}
        assert lite.manifest.agent_type == sample_egg.manifest.agent_type
        assert len(lite.skills.skills) == len(sample_egg.skills.skills)


class TestCorruptedEgg:
    def test_missing_manifest(self, tmp_path: Path):
        egg_path = tmp_path / "no_manifest.egg"
        with zipfile.ZipFile(egg_path, "w") as zf:
            zf.writestr("memory.json", '{"memory": []}')
        with pytest.raises(EggError, match="Invalid Egg"):
            load(egg_path)

    def test_missing_modules(self, tmp_path: Path):
        egg_path = tmp_path / "no_modules.egg"
        manifest = {
            "nydus_version": "0.1.0",
            "egg_version": "1.0",
            "created_at": datetime.now(UTC).isoformat(),
            "agent_type": "openclaw",
            "included_modules": [],
            "source_metadata": {},
        }
        with zipfile.ZipFile(egg_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
        with pytest.raises(EggError, match="Invalid Egg"):
            load(egg_path)

    def test_invalid_json_in_manifest(self, tmp_path: Path):
        egg_path = tmp_path / "bad_json.egg"
        with zipfile.ZipFile(egg_path, "w") as zf:
            zf.writestr("manifest.json", "{not valid json")
            zf.writestr("memory.json", '{"memory": []}')
            zf.writestr("secrets.json", '{"secrets": []}')
        with pytest.raises((EggError, Exception)):
            load(egg_path)

    def test_empty_zip(self, tmp_path: Path):
        egg_path = tmp_path / "empty.egg"
        with zipfile.ZipFile(egg_path, "w"):
            pass
        with pytest.raises(EggError, match="Invalid Egg"):
            load(egg_path)

    def test_truncated_zip(self, tmp_path: Path):
        egg_path = tmp_path / "truncated.egg"
        valid = tmp_path / "valid.egg"
        _make_minimal_egg(valid)
        data = valid.read_bytes()
        egg_path.write_bytes(data[: len(data) // 2])
        with pytest.raises((EggError, Exception)):
            load(egg_path)


def _make_minimal_egg(path: Path) -> None:
    """Create a minimal valid .egg archive."""
    manifest = {
        "nydus_version": "0.1.0",
        "egg_version": "2.0",
        "created_at": datetime.now(UTC).isoformat(),
        "agent_type": "openclaw",
        "included_modules": [],
        "source_metadata": {},
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("memory.json", '{"memory": []}')
        zf.writestr("secrets.json", '{"secrets": []}')
