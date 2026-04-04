# Troubleshooting

Common issues and solutions when working with PyNydus.

## Gitleaks

### "gitleaks binary was not found"

Spawning with `REDACT true` (the default) requires gitleaks on PATH.

```bash
# macOS
brew install gitleaks

# Verify
gitleaks version
```

Or point to a custom location:

```bash
export NYDUS_GITLEAKS_PATH=/path/to/gitleaks
```

To skip secret scanning entirely, set `REDACT false` in your Nydusfile — but
this means secrets will be included in the Egg in plaintext.

### Gitleaks finds no secrets (false negatives)

Gitleaks detection depends on entropy checks and pattern rules. Some synthetic
or low-entropy tokens may not be detected. If a known secret is not being
caught:

- Verify gitleaks works standalone: `echo 'aws_access_key_id = AKIAEXAMPLE' > test.txt && gitleaks directory . --no-banner`
- Check your gitleaks version: `gitleaks version` (v8.18+ recommended)
- On macOS, `/tmp` is a symlink to `/private/tmp` — gitleaks may skip
  symlinked directories. The pipeline uses `tempfile.TemporaryDirectory` which
  resolves this automatically.

### Gitleaks is slow

Gitleaks scans all files matching the spawner's `FILE_PATTERNS`. Large source
directories with many non-text files will slow it down. Use `REMOVE file <glob>`
in your Nydusfile to exclude irrelevant files before scanning.

## LLM refinement

### Refinement is silently skipped

LLM refinement requires **both** environment variables:

```bash
NYDUS_LLM_TYPE=openai/gpt-4o
NYDUS_LLM_API_KEY=sk-your-key
```

If either is missing, refinement is skipped without error. If only one is set,
`load_config()` raises a `ValueError`.

The `NYDUS_LLM_TYPE` format is `provider/model` — the slash is required.

### LLM call fails gracefully

If the LLM API call fails (timeout, rate limit, bad response), the pipeline
continues with the original unrefined content. Check the spawn log
(`nydus inspect agent.egg --logs`) for `llm_call` entries with error details.

### Placeholders corrupted after refinement

The LLM is instructed to preserve `{{SECRET_NNN}}` and `{{PII_NNN}}` tokens.
If a placeholder is missing after refinement, the LLM may have rewritten it.
This is a known edge case with weaker models. Use a higher-quality model or
disable refinement for that run.

## Hatching

### "passthrough requires the target to match the egg agent type"

Passthrough mode replays the raw source snapshot verbatim, so it only works
when the target platform matches the source platform. Use `rebuild` mode
(the default) for cross-platform hatching.

### "passthrough requires non-empty raw artifacts"

The egg was saved without the `raw/` directory, or it was loaded with
`include_raw=False`. Reload with `ny.load(path, include_raw=True)` or use
rebuild mode.

### Missing secrets at hatch time

If you see "Missing required secrets in agent.env", the `.env` file doesn't
contain all secrets marked `required_at_hatch=True`. Generate a template:

```bash
nydus env agent.egg -o agent.env
# Fill in the real values, then hatch
nydus hatch agent.egg --target letta --secrets agent.env
```

### "This egg requires nydus >= X.Y.Z"

The egg was created with a newer version of PyNydus. Upgrade:

```bash
pip install --upgrade pynydus
```

## Signing

### "No private key found"

Egg signing requires an Ed25519 private key. Generate one:

```bash
nydus keygen
```

This creates `~/.nydus/nydus_ed25519` (private) and `~/.nydus/nydus_ed25519.pub`
(public). The spawn command auto-signs when a key is available.

You can also set the key via environment variable:

```bash
export NYDUS_PRIVATE_KEY=/path/to/key
```

### Verification fails after editing an egg

Eggs are signed over their content. Any modification after signing (even
whitespace changes) will invalidate the signature. Re-spawn to create a new
signed egg.

## Nydusfile

### "Only one SOURCE directive is allowed"

The current version supports exactly one `SOURCE` per Nydusfile. To combine
multiple sources, use `FROM` with a base egg:

```
FROM nydus/openclaw:0.3.0
SOURCE letta ./my-letta-agent/
```

### Directive not taking effect

- `EXCLUDE` operates on memory labels (`persona`, `flow`, `context`, `state`),
  not filenames. To exclude files, use `REMOVE file <glob>`.
- `REMOVE skill ...` / `REMOVE memory ...` are merger operations that only
  apply when `FROM` is present. They operate on the base egg content, not the
  source files.
- `LABEL` overrides are applied after parsing, using source_store pattern
  matching.

## Tests

### Integration tests fail without gitleaks

Integration tests exercise the full pipeline including real redaction. Install
gitleaks or run only unit tests:

```bash
make test-unit
```

### Live LLM tests skip

These tests require real API credentials in a `.env` file:

```bash
cp .env.example .env
# Add your API key
make test-live-llm
```
