"""Edge case and error path tests (Priority 4.2).

Covers: corrupted eggs, empty sources, secrets-only, unicode/binary content,
malformed archives, boundary conditions.
"""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pynydus.api.errors import EggError, HatchError
from pynydus.api.schemas import (
    Bucket,
    Egg,
    Manifest,
    MemoryModule,
    SecretsModule,
    SkillsModule,
    SourceType,
)
from pynydus.engine.packager import pack, unpack


# ---------------------------------------------------------------------------
# Corrupted / malformed .egg files
# ---------------------------------------------------------------------------


class TestCorruptedEgg:
    def test_not_a_zip(self, tmp_path: Path):
        bad = tmp_path / "bad.egg"
        bad.write_text("this is not a zip file")
        with pytest.raises(EggError, match="Invalid Egg"):
            unpack(bad)

    def test_missing_manifest(self, tmp_path: Path):
        """Zip exists but has no manifest.json."""
        egg_path = tmp_path / "no_manifest.egg"
        with zipfile.ZipFile(egg_path, "w") as zf:
            zf.writestr("memory.json", '{"memory": []}')
        with pytest.raises(EggError, match="Invalid Egg"):
            unpack(egg_path)

    def test_missing_modules(self, tmp_path: Path):
        """Zip has manifest but missing module files."""
        egg_path = tmp_path / "no_modules.egg"
        manifest = {
            "nydus_version": "0.1.0",
            "egg_version": "1.0",
            "created_at": datetime.now(UTC).isoformat(),
            "source_type": "openclaw",
            "source_connector": "openclaw",
            "included_modules": [],
            "source_metadata": {},
        }
        with zipfile.ZipFile(egg_path, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
        with pytest.raises(EggError, match="Invalid Egg"):
            unpack(egg_path)

    def test_invalid_json_in_manifest(self, tmp_path: Path):
        """Manifest contains invalid JSON."""
        egg_path = tmp_path / "bad_json.egg"
        with zipfile.ZipFile(egg_path, "w") as zf:
            zf.writestr("manifest.json", "{not valid json")
            zf.writestr("memory.json", '{"memory": []}')
            zf.writestr("secrets.json", '{"secrets": []}')
        with pytest.raises((EggError, Exception)):
            unpack(egg_path)

    def test_nonexistent_egg(self, tmp_path: Path):
        with pytest.raises(EggError, match="not found"):
            unpack(tmp_path / "does_not_exist.egg")

    def test_empty_zip(self, tmp_path: Path):
        """Valid zip file but empty."""
        egg_path = tmp_path / "empty.egg"
        with zipfile.ZipFile(egg_path, "w"):
            pass
        with pytest.raises(EggError, match="Invalid Egg"):
            unpack(egg_path)

    def test_truncated_zip(self, tmp_path: Path):
        """Zip file that was truncated mid-write."""
        egg_path = tmp_path / "truncated.egg"
        # Create a valid zip, then truncate it
        valid = tmp_path / "valid.egg"
        _make_minimal_egg(valid)
        data = valid.read_bytes()
        egg_path.write_bytes(data[: len(data) // 2])
        with pytest.raises((EggError, Exception)):
            unpack(egg_path)


# ---------------------------------------------------------------------------
# Empty source directories
# ---------------------------------------------------------------------------


class TestEmptySource:
    def test_empty_directory_openclaw(self, tmp_path: Path):
        """Spawn from an empty directory produces an egg with no records."""
        from pynydus.engine.pipeline import build as spawn

        egg, raw, logs = spawn(tmp_path, source_type="openclaw")
        assert len(egg.skills.skills) == 0
        assert len(egg.memory.memory) == 0
        # Should still produce a valid egg
        assert egg.manifest.source_type == SourceType.OPENCLAW

    def test_directory_with_only_empty_files(self, tmp_path: Path):
        """Source directory has files but they're all empty."""
        from pynydus.engine.pipeline import build as spawn

        (tmp_path / "soul.md").write_text("")
        (tmp_path / "knowledge.md").write_text("")
        egg, raw, logs = spawn(tmp_path, source_type="openclaw")
        # Empty files should produce no meaningful records
        assert isinstance(egg, Egg)


# ---------------------------------------------------------------------------
# Source with only secrets (no skills, no memory)
# ---------------------------------------------------------------------------


class TestSecretsOnly:
    def test_spawn_with_pii_only(self, tmp_path: Path):
        """Source containing only PII data produces secrets but minimal memory."""
        from pynydus.engine.pipeline import build as spawn

        (tmp_path / "soul.md").write_text(
            "# Soul\n"
            "Contact: john.doe@example.com, phone 555-123-4567\n"
            "SSN: 123-45-6789\n"
        )
        egg, raw, logs = spawn(tmp_path, source_type="openclaw")
        # Should have some secrets from PII redaction
        assert len(egg.secrets.secrets) > 0

    def test_exclude_all_buckets_except_secrets(self, tmp_path: Path):
        """Using Nydusfile to only include secrets bucket."""
        from pynydus.engine.nydusfile import NydusfileConfig
        from pynydus.engine.pipeline import build as spawn

        (tmp_path / "soul.md").write_text(
            "# Soul\nMy API key is sk-12345 and email is test@example.com"
        )
        config = NydusfileConfig(
            source=SourceType.OPENCLAW,
            include={Bucket.SECRETS},
        )
        egg, raw, logs = spawn(
            tmp_path, source_type="openclaw", nydusfile_config=config
        )
        assert len(egg.skills.skills) == 0
        assert len(egg.memory.memory) == 0


# ---------------------------------------------------------------------------
# Unicode content
# ---------------------------------------------------------------------------


class TestUnicodeContent:
    def test_unicode_in_source_files(self, tmp_path: Path):
        """Source files with non-ASCII characters."""
        from pynydus.engine.pipeline import build as spawn

        (tmp_path / "soul.md").write_text(
            "# Soul\n"
            "I speak 日本語, العربية, and émojis 🎉🚀\n"
            "Mathematical: ∑∫∂√π\n"
        )
        egg, raw, logs = spawn(tmp_path, source_type="openclaw")
        # Should handle unicode without errors
        assert isinstance(egg, Egg)
        # Memory should contain the unicode text
        assert any("日本語" in r.text for r in egg.memory.memory)

    def test_unicode_in_skill_content(self, tmp_path: Path):
        """Skills directory with unicode content."""
        from pynydus.engine.pipeline import build as spawn

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "greet.md").write_text(
            "# Greet\nSay こんにちは to the user."
        )
        egg, raw, logs = spawn(tmp_path, source_type="openclaw")
        assert any("こんにちは" in s.content for s in egg.skills.skills)

    def test_unicode_roundtrip_pack_unpack(self, tmp_path: Path):
        """Unicode content survives pack → unpack cycle."""
        from pynydus.engine.pipeline import build as spawn
        from pynydus.engine.packager import pack_with_raw

        (tmp_path / "soul.md").write_text("# Soul\nUnicode: café résumé naïve")
        egg, raw, logs = spawn(tmp_path, source_type="openclaw")

        egg_path = tmp_path / "unicode.egg"
        pack_with_raw(egg, egg_path, raw, spawn_log=logs.get("spawn_log"))

        restored = unpack(egg_path)
        # Find memory record with unicode
        has_unicode = any("café" in r.text for r in restored.memory.memory)
        assert has_unicode


# ---------------------------------------------------------------------------
# Pack / unpack boundary conditions
# ---------------------------------------------------------------------------


class TestPackUnpackBoundary:
    def test_very_long_text(self, tmp_path: Path):
        """Source file with very long text content."""
        from pynydus.engine.pipeline import build as spawn

        long_text = "This is a sentence. " * 5000  # ~100K chars
        (tmp_path / "soul.md").write_text(f"# Soul\n{long_text}")
        egg, raw, logs = spawn(tmp_path, source_type="openclaw")
        assert isinstance(egg, Egg)

    def test_many_small_files(self, tmp_path: Path):
        """Source with many small files — all end up as raw artifacts."""
        from pynydus.engine.pipeline import build as spawn

        for i in range(50):
            (tmp_path / f"note_{i:03d}.md").write_text(f"# Note {i}\nContent {i}.")
        egg, raw, logs = spawn(tmp_path, source_type="openclaw")
        # OpenClaw only processes known files (soul.md, etc.) as memory,
        # but all .md files become raw artifacts
        assert len(raw) >= 50

    def test_overwrite_existing_egg(self, tmp_path: Path):
        """Packing over an existing .egg replaces it."""
        from pynydus.engine.pipeline import build as spawn
        from pynydus.engine.packager import pack_with_raw

        (tmp_path / "soul.md").write_text("# Soul\nVersion 1")
        egg1, raw1, logs1 = spawn(tmp_path, source_type="openclaw")

        egg_path = tmp_path / "test.egg"
        pack_with_raw(egg1, egg_path, raw1)
        size1 = egg_path.stat().st_size

        # Add more files to make a bigger egg
        (tmp_path / "extra.md").write_text("# Extra\nMore content here.")
        egg2, raw2, logs2 = spawn(tmp_path, source_type="openclaw")
        pack_with_raw(egg2, egg_path, raw2)
        size2 = egg_path.stat().st_size

        # Second pack should have more raw artifacts
        assert len(raw2) > len(raw1)
        # File was overwritten
        assert egg_path.exists()


# ---------------------------------------------------------------------------
# Version compatibility edge cases
# ---------------------------------------------------------------------------


class TestVersionCompatEdgeCases:
    def test_hatch_egg_with_future_version(self, tmp_path: Path):
        """Hatching an egg that requires a future version should fail."""
        from pynydus.engine.hatcher import hatch

        egg = Egg(
            manifest=Manifest(
                nydus_version="99.0.0",
                min_nydus_version="99.0.0",
                created_at=datetime.now(UTC),
                source_type=SourceType.OPENCLAW,
                included_modules=["skills"],
                source_metadata={},
            ),
            skills=SkillsModule(skills=[]),
            memory=MemoryModule(memory=[]),
            secrets=SecretsModule(secrets=[]),
        )
        with pytest.raises(HatchError, match="requires nydus >= 99.0.0"):
            hatch(egg, target="openclaw", output_dir=tmp_path / "out")


# ---------------------------------------------------------------------------
# Signing edge cases
# ---------------------------------------------------------------------------


class TestSigningEdgeCases:
    def test_verify_unsigned_returns_none(self, tmp_path: Path):
        from pynydus.engine.packager import pack_with_raw, verify_egg_archive
        from pynydus.engine.pipeline import build as spawn

        (tmp_path / "soul.md").write_text("# Soul\nTest")
        egg, raw, logs = spawn(tmp_path, source_type="openclaw")
        egg_path = tmp_path / "test.egg"
        pack_with_raw(egg, egg_path, raw)
        assert verify_egg_archive(egg_path) is None

    def test_signed_egg_verifies(self, tmp_path: Path):
        from pynydus.engine.packager import pack_with_raw, verify_egg_archive
        from pynydus.engine.pipeline import build as spawn
        from pynydus.pkg.signing import generate_keypair, load_private_key

        key_dir = tmp_path / "keys"
        generate_keypair(key_dir)
        private_key = load_private_key(key_dir / "private.pem")

        (tmp_path / "soul.md").write_text("# Soul\nTest")
        egg, raw, logs = spawn(tmp_path, source_type="openclaw")
        egg_path = tmp_path / "signed.egg"
        pack_with_raw(egg, egg_path, raw, private_key=private_key)
        assert verify_egg_archive(egg_path) is True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_egg(path: Path) -> None:
    """Create a minimal valid .egg archive."""
    manifest = {
        "nydus_version": "0.1.0",
        "egg_version": "2.0",
        "created_at": datetime.now(UTC).isoformat(),
        "source_type": "openclaw",
        "source_connector": "openclaw",
        "included_modules": [],
        "source_metadata": {},
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("memory.json", '{"memory": []}')
        zf.writestr("secrets.json", '{"secrets": []}')
