"""Ed25519 egg signing and verification. Spec §signing.

Provides asymmetric signing so recipients can verify that an egg was created
by a known author and has not been modified in transit.

Key storage convention:
    Private key: ~/.nydus/keys/private.pem  (or NYDUS_PRIVATE_KEY env var)
    Public key:  embedded in signature.json inside the .egg archive
"""

from __future__ import annotations

import hashlib
import json
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
    """Generate a new Ed25519 keypair and write to disk.

    Returns (private_key_path, public_key_path).
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

    pub_path.write_bytes(
        public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    )

    return priv_path, pub_path


# ---------------------------------------------------------------------------
# Key loading
# ---------------------------------------------------------------------------


def load_private_key(path: Path | None = None) -> Ed25519PrivateKey:
    """Load an Ed25519 private key from PEM file or NYDUS_PRIVATE_KEY env var."""
    env_key = os.environ.get("NYDUS_PRIVATE_KEY")
    if env_key:
        return load_pem_private_key(env_key.encode(), password=None)  # type: ignore[return-value]

    path = path or DEFAULT_PRIVATE_KEY_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Private key not found: {path}\n"
            f"Run 'nydus keygen' to generate a keypair."
        )
    return load_pem_private_key(path.read_bytes(), password=None)  # type: ignore[return-value]


def load_public_key(pem_bytes: bytes) -> Ed25519PublicKey:
    """Load an Ed25519 public key from PEM bytes."""
    return load_pem_public_key(pem_bytes)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------


def _canonical_content(content_parts: list[bytes]) -> bytes:
    """Create a deterministic byte string from ordered content parts.

    Each part is length-prefixed to prevent ambiguity:
        <8-byte big-endian length><content>
    """
    buf = bytearray()
    for part in content_parts:
        buf.extend(len(part).to_bytes(8, "big"))
        buf.extend(part)
    return bytes(buf)


def compute_content_hash(content_parts: list[bytes]) -> bytes:
    """SHA-256 hash of canonical content."""
    canonical = _canonical_content(content_parts)
    return hashlib.sha256(canonical).digest()


# ---------------------------------------------------------------------------
# Signing / verification
# ---------------------------------------------------------------------------


def sign_egg_content(
    private_key: Ed25519PrivateKey,
    content_parts: list[bytes],
) -> dict:
    """Sign egg content and return a signature.json-compatible dict.

    ``content_parts`` should be the ordered list:
        [manifest_json, skills_json, memory_json, secrets_json]

    Returns a dict with:
        - algorithm: "Ed25519"
        - content_hash: hex SHA-256 of canonical content
        - signature: base64-encoded Ed25519 signature over the content hash
        - public_key: PEM-encoded public key (for verification without external key)
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
    """Verify an egg signature against its content.

    Returns True if valid, raises on tampered content.
    """
    from cryptography.exceptions import InvalidSignature

    # Recompute content hash
    content_hash = compute_content_hash(content_parts)

    # Check content hash matches
    if content_hash.hex() != signature_data["content_hash"]:
        return False

    # Verify Ed25519 signature
    public_key = load_public_key(signature_data["public_key"].encode("ascii"))
    signature = b64decode(signature_data["signature"])

    try:
        public_key.verify(signature, content_hash)
    except InvalidSignature:
        return False

    return True
