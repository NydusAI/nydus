# Installation

## PyNydus

Requires Python 3.10+.

```bash
pip install pynydus
```

## Gitleaks (external)

Spawning with `REDACT true` (the default) requires
[gitleaks](https://github.com/gitleaks/gitleaks) for secret scanning:

```bash
# macOS
brew install gitleaks

# Linux
curl -sSL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_8.21.2_linux_x64.tar.gz \
  | tar xz -C /usr/local/bin gitleaks

# From source (requires Go 1.22+)
go install github.com/gitleaks/gitleaks/v8@latest
```

If the binary is not on `$PATH`, set `NYDUS_GITLEAKS_PATH`:

```bash
export NYDUS_GITLEAKS_PATH=/path/to/gitleaks
```

Hatching and `FROM`-only spawns (without `SOURCE`) do **not** require gitleaks.
