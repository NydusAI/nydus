"""Ed25519 egg signing and verification. Spec §signing.

Provides asymmetric signing so recipients can verify that an egg was created
by a known author and has not been modified in transit.

Key storage convention:
    Private key: ~/.nydus/keys/private.pem  (or NYDUS_PRIVATE_KEY env var)
    Public key:  embedded in signature.json inside the .egg archive
"""

from __future__ import annotations

import hashlib
import os
from base64 import b64decode, b64encode
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)

# ---------------------------------------------------------------------------
# Key paths
# ---------------------------------------------------------------------------

DEFAULT_KEY_DIR = Path.home() / ".nydus" / "keys"
DEFAULT_PRIVATE_KEY_PATH = DEFAULT_KEY_DIR / "private.pem"
DEFAULT_PUBLIC_KEY_PATH = DEFAULT_KEY_DIR / "public.pem"


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


def generate_keypair(
    key_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Generate a new Ed25519 keypair and write PEM files to disk.

    Args:
        key_dir: Directory for ``private.pem`` and ``public.pem``. Defaults to
            ``~/.nydus/keys``.

    Returns:
        ``(private_key_path, public_key_path)``.
    """
    key_dir = key_dir or DEFAULT_KEY_DIR
    key_dir.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    priv_path = key_dir / "private.pem"
    pub_path = key_dir / "public.pem"

    priv_path.write_bytes(
        private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    priv_path.chmod(0o600)

    pub_path.write_bytes(public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo))

    return priv_path, pub_path


# ---------------------------------------------------------------------------
# Key loading
# ---------------------------------------------------------------------------


def load_private_key(path: Path | None = None) -> Ed25519PrivateKey:
    """Load an Ed25519 private key from PEM file or ``NYDUS_PRIVATE_KEY``.

    Args:
        path: PEM file path. Ignored when ``NYDUS_PRIVATE_KEY`` is set.

    Returns:
        Parsed private key.

    Raises:
        FileNotFoundError: If no env key and *path* (default key path) is missing.
    """
    env_key = os.environ.get("NYDUS_PRIVATE_KEY")
    if env_key:
        return load_pem_private_key(env_key.encode(), password=None)  # type: ignore[return-value]

    path = path or DEFAULT_PRIVATE_KEY_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Private key not found: {path}\nRun 'nydus keygen' to generate a keypair."
        )
    return load_pem_private_key(path.read_bytes(), password=None)  # type: ignore[return-value]


def load_public_key(pem_bytes: bytes) -> Ed25519PublicKey:
    """Load an Ed25519 public key from PEM-encoded bytes.

    Args:
        pem_bytes: PEM text as UTF-8 bytes.

    Returns:
        Parsed public key.
    """
    return load_pem_public_key(pem_bytes)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------


def _canonical_content(content_parts: list[bytes]) -> bytes:
    """Concatenate content parts with length prefixes (big-endian 8-byte length).

    Args:
        content_parts: Ordered binary blobs to hash.

    Returns:
        Canonical byte string suitable for signing.
    """
    buf = bytearray()
    for part in content_parts:
        buf.extend(len(part).to_bytes(8, "big"))
        buf.extend(part)
    return bytes(buf)


def compute_content_hash(content_parts: list[bytes]) -> bytes:
    """Return SHA-256 of ``_canonical_content`` output.

    Args:
        content_parts: Same ordered parts as used for signing.

    Returns:
        32-byte digest.
    """
    canonical = _canonical_content(content_parts)
    return hashlib.sha256(canonical).digest()


# ---------------------------------------------------------------------------
# Signing / verification
# ---------------------------------------------------------------------------


def sign_egg_content(
    private_key: Ed25519PrivateKey,
    content_parts: list[bytes],
) -> dict:
    """Sign egg content and return a ``signature.json``-compatible dict.

    Args:
        private_key: Key used to sign.
        content_parts: Ordered blobs, typically
            ``[manifest_json, skills_json, memory_json, secrets_json]``.

    Returns:
        Dict with ``algorithm``, ``content_hash`` (hex), ``signature`` (base64),
        and ``public_key`` (PEM) for offline verification.
    """
    content_hash = compute_content_hash(content_parts)
    signature = private_key.sign(content_hash)
    public_key = private_key.public_key()

    return {
        "algorithm": "Ed25519",
        "content_hash": content_hash.hex(),
        "signature": b64encode(signature).decode("ascii"),
        "public_key": public_key.public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        ).decode("ascii"),
    }


def verify_egg_content(
    signature_data: dict,
    content_parts: list[bytes],
) -> bool:
    """Verify an egg signature dict against recomputed content.

    Args:
        signature_data: Parsed ``signature.json`` payload.
        content_parts: Same ordered parts used when signing.

    Returns:
        ``True`` if hash and Ed25519 signature match. ``False`` if hash or
        signature check fails.
    """
    from cryptography.exceptions import InvalidSignature

    content_hash = compute_content_hash(content_parts)

    if content_hash.hex() != signature_data["content_hash"]:
        return False

    public_key = load_public_key(signature_data["public_key"].encode("ascii"))
    signature = b64decode(signature_data["signature"])

    try:
        public_key.verify(signature, content_hash)
    except InvalidSignature:
        return False

    return True
