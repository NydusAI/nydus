"""Tests for Ed25519 egg signing and verification."""

import zipfile
from pathlib import Path

import pytest
from pynydus.api.schemas import Egg
from pynydus.engine.packager import (
    EMBEDDED_NYDUSFILE_NAME,
    load,
    read_nydusfile,
    read_signature,
    save,
    verify_egg_archive,
)
from pynydus.security.signing import (
    compute_content_hash,
    generate_keypair,
    load_private_key,
    sign_egg_content,
    verify_egg_content,
)

# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


class TestKeygen:
    def test_generate_keypair(self, tmp_path: Path):
        priv_path, pub_path = generate_keypair(tmp_path)
        assert priv_path.exists()
        assert pub_path.exists()
        assert priv_path.name == "private.pem"
        assert pub_path.name == "public.pem"

    def test_private_key_permissions(self, tmp_path: Path):
        priv_path, _ = generate_keypair(tmp_path)
        mode = priv_path.stat().st_mode & 0o777
        assert mode == 0o600

    def test_load_private_key(self, tmp_path: Path):
        generate_keypair(tmp_path)
        key = load_private_key(tmp_path / "private.pem")
        assert key is not None

    def test_load_private_key_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="Private key not found"):
            load_private_key(tmp_path / "nonexistent.pem")

    def test_load_from_env(self, tmp_path: Path, monkeypatch):
        priv_path, _ = generate_keypair(tmp_path)
        pem_data = priv_path.read_text()
        monkeypatch.setenv("NYDUS_PRIVATE_KEY", pem_data)
        key = load_private_key()  # Should use env var, not default path
        assert key is not None


# ---------------------------------------------------------------------------
# Signing and verification (low-level)
# ---------------------------------------------------------------------------


class TestSignVerify:
    def test_sign_and_verify(self, tmp_path: Path):
        priv_path, _ = generate_keypair(tmp_path)
        private_key = load_private_key(priv_path)

        parts = [b"manifest", b"skills", b"memory", b"secrets"]
        sig_data = sign_egg_content(private_key, parts)

        assert sig_data["algorithm"] == "Ed25519"
        assert "content_hash" in sig_data
        assert "signature" in sig_data
        assert "public_key" in sig_data

        assert verify_egg_content(sig_data, parts) is True

    def test_tampered_content_fails(self, tmp_path: Path):
        priv_path, _ = generate_keypair(tmp_path)
        private_key = load_private_key(priv_path)

        parts = [b"manifest", b"skills", b"memory", b"secrets"]
        sig_data = sign_egg_content(private_key, parts)

        # Tamper with one part
        tampered = [b"TAMPERED", b"skills", b"memory", b"secrets"]
        assert verify_egg_content(sig_data, tampered) is False

    def test_tampered_hash_fails(self, tmp_path: Path):
        priv_path, _ = generate_keypair(tmp_path)
        private_key = load_private_key(priv_path)

        parts = [b"manifest", b"skills", b"memory", b"secrets"]
        sig_data = sign_egg_content(private_key, parts)

        # Tamper with the stored hash
        sig_data["content_hash"] = "0" * 64
        assert verify_egg_content(sig_data, parts) is False

    def test_different_keys_fail(self, tmp_path: Path):
        """Signature from key A cannot be verified with key B's public key."""
        key_a_dir = tmp_path / "a"
        key_b_dir = tmp_path / "b"
        generate_keypair(key_a_dir)
        generate_keypair(key_b_dir)

        private_a = load_private_key(key_a_dir / "private.pem")
        private_b = load_private_key(key_b_dir / "private.pem")

        parts = [b"manifest", b"skills", b"memory", b"secrets"]
        sig_data = sign_egg_content(private_a, parts)

        # Replace public key with key B's
        pub_b = private_b.public_key()
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PublicFormat,
        )

        sig_data["public_key"] = pub_b.public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        ).decode("ascii")

        assert verify_egg_content(sig_data, parts) is False

    def test_content_hash_deterministic(self):
        parts = [b"a", b"b", b"c"]
        h1 = compute_content_hash(parts)
        h2 = compute_content_hash(parts)
        assert h1 == h2

    def test_content_hash_order_matters(self):
        h1 = compute_content_hash([b"a", b"b"])
        h2 = compute_content_hash([b"b", b"a"])
        assert h1 != h2

    def test_corrupted_sig(self, tmp_path: Path):
        priv_path, _ = generate_keypair(tmp_path)
        private_key = load_private_key(priv_path)
        parts = [b"a", b"b"]
        sig_data = sign_egg_content(private_key, parts)
        sig_data["signature"] = "deadbeef" * 16
        assert verify_egg_content(sig_data, parts) is False

    def test_empty_parts(self, tmp_path: Path):
        priv_path, _ = generate_keypair(tmp_path)
        private_key = load_private_key(priv_path)
        parts: list[bytes] = []
        sig_data = sign_egg_content(private_key, parts)
        assert verify_egg_content(sig_data, parts) is True


# ---------------------------------------------------------------------------
# Packager integration — signed eggs
# ---------------------------------------------------------------------------


class TestSignedEggArchive:
    def test_unsigned_egg_has_no_signature(self, sample_egg: Egg, tmp_path: Path):
        path = save(sample_egg, tmp_path / "test.egg")
        assert read_signature(path) is None
        egg = load(path)
        assert egg.manifest.signature == ""

    def test_signed_egg_has_signature(self, sample_egg: Egg, tmp_path: Path):
        key_dir = tmp_path / "keys"
        generate_keypair(key_dir)
        private_key = load_private_key(key_dir / "private.pem")

        path = save(sample_egg, tmp_path / "test.egg", private_key=private_key)
        sig = read_signature(path)
        assert sig is not None
        assert sig["algorithm"] == "Ed25519"

        egg = load(path)
        assert egg.manifest.signature != ""
        assert egg.manifest.signature == sig["signature"]

    def test_signed_egg_verifies(self, sample_egg: Egg, tmp_path: Path):
        key_dir = tmp_path / "keys"
        generate_keypair(key_dir)
        private_key = load_private_key(key_dir / "private.pem")

        path = save(sample_egg, tmp_path / "test.egg", private_key=private_key)
        assert verify_egg_archive(path) is True

    def test_unsigned_egg_verify_returns_none(self, sample_egg: Egg, tmp_path: Path):
        path = save(sample_egg, tmp_path / "test.egg")
        assert verify_egg_archive(path) is None

    def test_tampered_egg_fails_verification(self, sample_egg: Egg, tmp_path: Path):
        key_dir = tmp_path / "keys"
        generate_keypair(key_dir)
        private_key = load_private_key(key_dir / "private.pem")

        path = save(sample_egg, tmp_path / "test.egg", private_key=private_key)

        # Tamper with memory.json inside the archive
        _tamper_archive_entry(path, "memory.json", b'{"memory": []}')

        assert verify_egg_archive(path) is False

    def test_tampered_manifest_fails(self, sample_egg: Egg, tmp_path: Path):
        key_dir = tmp_path / "keys"
        generate_keypair(key_dir)
        private_key = load_private_key(key_dir / "private.pem")

        path = save(sample_egg, tmp_path / "test.egg", private_key=private_key)

        # Tamper with manifest.json
        _tamper_archive_entry(path, "manifest.json", b'{"nydus_version": "EVIL"}')

        assert verify_egg_archive(path) is False

    def test_signed_egg_with_raw_and_logs(self, sample_egg: Egg, tmp_path: Path):
        """Signing works alongside raw artifacts and spawn logs."""
        key_dir = tmp_path / "keys"
        generate_keypair(key_dir)
        private_key = load_private_key(key_dir / "private.pem")

        raw = {"soul.md": "I am an agent."}
        log = [{"type": "redaction", "source": "memory:m1", "pii_type": "EMAIL"}]

        path = save(
            sample_egg,
            tmp_path / "test.egg",
            raw_artifacts=raw,
            spawn_log=log,
            private_key=private_key,
        )
        assert verify_egg_archive(path) is True


# ---------------------------------------------------------------------------
# Nydusfile inclusion in egg archive
# ---------------------------------------------------------------------------


class TestNydusfileInclusion:
    def test_nydusfile_included(self, sample_egg: Egg, tmp_path: Path):
        nf_text = "SOURCE openclaw ./src\nLABEL version 1.0\n"
        path = save(
            sample_egg,
            tmp_path / "test.egg",
            nydusfile_text=nf_text,
        )
        assert read_nydusfile(path) == nf_text
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            assert EMBEDDED_NYDUSFILE_NAME in names
            assert "nydusfile" not in names

    def test_nydusfile_absent_when_not_provided(self, sample_egg: Egg, tmp_path: Path):
        path = save(sample_egg, tmp_path / "test.egg")
        assert read_nydusfile(path) is None

    def test_load_reads_embedded_nydusfile(self, sample_egg: Egg, tmp_path: Path):
        """load() includes embedded ``Nydusfile`` text on the Egg."""
        nf_text = "SOURCE openclaw ./src\n"
        path = save(
            sample_egg,
            tmp_path / "test.egg",
            nydusfile_text=nf_text,
        )
        egg = load(path)
        assert egg.nydusfile == nf_text
        assert egg.manifest.nydus_version == sample_egg.manifest.nydus_version
        assert len(egg.skills.skills) == 1
        assert len(egg.memory.memory) == 1

    def test_nydusfile_with_signed_egg(self, sample_egg: Egg, tmp_path: Path):
        key_dir = tmp_path / "keys"
        generate_keypair(key_dir)
        private_key = load_private_key(key_dir / "private.pem")

        nf_text = "SOURCE openclaw ./src\nSECRET API_KEY env\n"
        path = save(
            sample_egg,
            tmp_path / "test.egg",
            nydusfile_text=nf_text,
            private_key=private_key,
        )
        assert read_nydusfile(path) == nf_text
        assert verify_egg_archive(path) is True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tamper_archive_entry(egg_path: Path, entry_name: str, new_content: bytes) -> None:
    """Replace a single file inside a zip archive (for tamper testing)."""
    import shutil
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".egg", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    with zipfile.ZipFile(egg_path, "r") as zr:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zw:
            for item in zr.infolist():
                if item.filename == entry_name:
                    zw.writestr(item, new_content)
                else:
                    zw.writestr(item, zr.read(item.filename))

    shutil.move(str(tmp_path), str(egg_path))
