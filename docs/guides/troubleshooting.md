# Troubleshooting

## Gitleaks


### "gitleaks binary was not found"

Spawning with `REDACT true` (the default) requires gitleaks.
See {doc}`/getting-started/install` for setup instructions.

To skip secret scanning, set `REDACT false` in your Nydusfile, but secrets
will remain in plaintext.


### Gitleaks finds no secrets (false negatives)

- Verify standalone: `echo 'aws_access_key_id = AKIAEXAMPLE' > test.txt && gitleaks directory . --no-banner`
- Check version: `gitleaks version` (v8.18+ recommended)
- On macOS, `/tmp` symlink to `/private/tmp`. The pipeline handles this
  automatically via `tempfile.TemporaryDirectory`

### Gitleaks is slow

Use `REMOVE file <glob>` in your Nydusfile to exclude irrelevant files
before scanning.

## LLM refinement


### Refinement is silently skipped

Requires **both** `NYDUS_LLM_TYPE` and `NYDUS_LLM_API_KEY`.
See {doc}`/guides/configuration`.


### LLM call fails gracefully

The pipeline continues with unrefined content. Check the spawn log
(`nydus inspect agent.egg --logs`) for `llm_call` entries with error details.


### Placeholders corrupted after refinement

The LLM may rewrite `{{SECRET_NNN}}` tokens. Use a higher-quality model or
disable refinement for that run.

## Hatching


### "passthrough requires the target to match the egg agent type"

Passthrough replays the raw snapshot verbatim, so the target must match the source.
Use rebuild mode (default) for cross-platform hatching.


### "passthrough requires non-empty raw artifacts"

The egg was saved without `raw/` or loaded with `include_raw=False`. Reload
with `ny.load(path, include_raw=True)` or use rebuild mode.


### Missing secrets at hatch time

Generate a template and fill in values:

```bash
nydus env agent.egg -o agent.env
# fill in real values
nydus hatch agent.egg --target letta --secrets agent.env
```


### "This egg requires nydus >= X.Y.Z"

Upgrade: `pip install --upgrade pynydus`

## Signing


### "No private key found"

Generate a keypair: `nydus keygen`. See {doc}`/guides/security` for details.


### Verification fails after editing an egg

Any modification invalidates the signature. Re-spawn to create a new signed
egg.

## Nydusfile


### "Only one SOURCE directive is allowed"

Use `FROM` with a base egg to combine multiple sources (registry tag is only
an example. Use a version your Nest server provides, or `FROM ./base.egg`):

```text
FROM nydus/openclaw:0.3.0
SOURCE letta ./my-letta-agent/
```


### Directive not taking effect

- `EXCLUDE` operates on memory labels, not filenames. Use `REMOVE file <glob>`
  to exclude files.
- `REMOVE skill …` / `REMOVE memory …` are merger ops that require `FROM`.
- `LABEL` overrides are applied after parsing.

## Tests


### Integration tests fail without gitleaks

Install gitleaks or run only unit tests: `make test-unit`.


### Live LLM tests skip

Requires `.env` with API credentials. See {doc}`/guides/configuration`.
