# Common (`pynydus.common`)

Shared building blocks used across connectors and the public API.

## Enums (`pynydus.common.enums`)

```{autodoc2-object} pynydus.common.enums.Directive
```

## Connector utilities (`pynydus.common.connector_utils`)

Shared helpers used by multiple platform connectors:

- **`split_paragraphs(text)`** — splits text into non-empty paragraphs.
- **`parse_mcp_configs_from_files(files)`** — loads MCP server configs from a
  virtual file tree. Handles both Claude Desktop format (`mcpServers` wrapper)
  and legacy `mcp/<name>.json` per-server files.
- **`skill_to_filename(name)`** — converts a skill display name to a safe `.py`
  module filename.
- **`parse_timestamp(val)`** — parses ISO strings and Unix epochs into `datetime`.
- **`extract_date_from_filename(name)`** — extracts a `YYYY-MM-DD` date from
  filenames like `memory/2026-03-15.md`.
- **`date_key_from_record(rec)`** — extracts a date key from a `MemoryRecord`
  (timestamp or source_store filename).
- **`join_records(records)`** — joins memory records into a single file body.

## Generated modules

The {doc}`/apidocs/index` tree includes full pages for `pynydus.common.connector_utils`
and `pynydus.common.scan_paths` with every function and constant. All enums are also
listed under {doc}`/apidocs/pynydus/pynydus.common.enums`.
