# Egg Signing

Nydus uses Ed25519 asymmetric signatures so recipients can verify that an Egg
was created by a known author and has not been modified in transit.

## Generate a keypair

```bash
nydus keygen
```

This creates two files in `~/.nydus/keys/`:

| File | Purpose |
|------|---------|
| `private.pem` | Signs Eggs during `nydus spawn` (permissions 600, owner-only) |
| `public.pem` | Embedded in signed Eggs for verification |

You can specify a custom directory:

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

The `signature.json` file contains:

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

| Scenario | Behavior |
|----------|----------|
| Valid signature | "Signature verified." is printed, hatching proceeds |
| Invalid signature | Hatching is rejected with an error |
| Unsigned Egg | Hatching proceeds silently |

Check signature status without hatching:

```bash
nydus inspect agent.egg
```

The output includes one of: `signature: valid (Ed25519)`, `signature: INVALID`,
or `signature: unsigned`.

## SDK usage

```python
from pynydus import Nydus

ny = Nydus()
egg = ny.spawn()

# Sign during pack (requires private key)
ny.pack(egg, output="agent.egg", sign=True)
```

## Key management tips

- Keep `private.pem` secure. Do not commit it to version control.
- Distribute `public.pem` to anyone who needs to verify your Eggs.
- Use `NYDUS_PRIVATE_KEY` environment variable for CI/CD pipelines instead of
  relying on the default file path.
