# Egg Signing

Nydus uses Ed25519 asymmetric signatures so recipients can verify that an Egg
was created by a known author and has not been modified in transit.

## Generate a keypair

```bash
nydus keygen
```

This creates two files in `~/.nydus/keys/`:

- `private.pem`: used to sign Eggs (permissions set to 600, owner-only)
- `public.pem`: embedded in signed Eggs for verification

You can also specify a custom directory:

```bash
nydus keygen --dir ./my-keys/
```

## How signing works

When a private key exists at `~/.nydus/keys/private.pem` (or is set via the
`NYDUS_PRIVATE_KEY` environment variable), `nydus spawn` automatically signs
the Egg.

The signing process:

1. Serialize the Egg's `manifest.json`, `skills`, `memory.json`, and
   `secrets.json` into ordered byte arrays
2. Compute a SHA-256 hash over the canonical content (length-prefixed parts)
3. Sign the hash with the Ed25519 private key
4. Store the signature in both `manifest.signature` and a separate
   `signature.json` inside the `.egg` archive

The `signature.json` contains:

```json
{
  "algorithm": "Ed25519",
  "content_hash": "<hex SHA-256>",
  "signature": "<base64 Ed25519 signature>",
  "public_key": "<PEM-encoded public key>"
}
```

## Verification

Signature verification happens automatically during `nydus hatch`:

- **Valid signature**: "Signature verified." is printed, hatching proceeds
- **Invalid signature**: hatching is rejected with an error
- **Unsigned**: hatching proceeds silently (no warning by default)

You can also check signature status with `nydus inspect`:

```bash
nydus inspect agent.egg
```

The output includes: `signature: valid (Ed25519)`, `signature: INVALID`, or
`signature: unsigned`.

## SDK usage

```python
from pynydus import Nydus

ny = Nydus()
egg = ny.spawn()  # reads ./Nydusfile

# Sign the egg when packing
ny.pack(egg, output="agent.egg", sign=True)
```
