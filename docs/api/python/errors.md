# Errors

All Nydus exceptions inherit from `NydusError`.

## Exception hierarchy

`NydusError`
: Base error for all Nydus operations.

`NydusfileError`
: Error parsing or validating a Nydusfile. Has a `line` attribute indicating
  the source line number.

`ConnectorError`
: Error in a spawner or hatcher connector (e.g., unknown source type,
  unreadable input).

`EggError`
: Error reading, writing, or packaging an Egg (e.g., corrupted archive,
  missing modules).

`HatchError`
: Error during the hatching pipeline (e.g., missing required secrets,
  version incompatibility, invalid hatch `mode`, or `passthrough` requested when
  the target does not match the egg source or `raw/` is empty).

`ConfigError`
: Error in Nydus configuration (e.g., missing registry URL, invalid LLM
  config).

`GitleaksNotFoundError`
: Raised when spawning requires secret scanning (`REDACT true` with `SOURCE`
  directives) but the `gitleaks` CLI is not installed. Install gitleaks
  (<https://github.com/gitleaks/gitleaks>) or set `$NYDUS_GITLEAKS_PATH`.

`RegistryError`
: Error communicating with the Nest registry (e.g., HTTP failures, auth
  errors, SHA-256 mismatch).

All error classes are importable from `pynydus.api.errors`.

**Full exception reference (auto-generated):** {doc}`/apidocs/pynydus/pynydus.api.errors`
