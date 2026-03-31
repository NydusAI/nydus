# API Reference

Python API reference for the `pynydus` package. This section covers the client
SDK, core data models, spawner/hatcher types, and error hierarchy.

All public types are importable from `pynydus` or their respective submodules.

## Package layout

```text
pynydus/
  __init__.py         # re-exports Nydus, Egg, MemoryLabel, etc.
  client/client.py    # Nydus client class
  api/schemas.py      # Egg, Manifest, records, enums
  api/raw_types.py    # ParseResult, RenderResult, RawSkill, RawMemory
  api/errors.py       # Exception hierarchy
  agents/             # Framework-specific spawners and hatchers
  engine/             # Pipeline internals (spawn, hatch, pack, validate, diff)
  pkg/                # Utilities (presidio, LLM, signing, config)
  cmd/                # CLI (Typer app)
  remote/             # Nest registry client
```

```{toctree}
:maxdepth: 2

client
schemas
raw_types
errors
```
