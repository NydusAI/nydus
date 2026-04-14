# Protocols (`pynydus.api.protocols`)

Abstract base classes that all platform connectors must subclass.

## Spawner

```{autodoc2-object} pynydus.api.protocols.Spawner
```

All spawners must implement `parse(files: dict[str, str]) -> ParseResult`.
The method receives pre-redacted file contents (placeholder tokens instead of
real secrets) and returns structured records.

Concrete implementations: `OpenClawSpawner`, `ZeroClawSpawner`, `LettaSpawner`.

## Hatcher

```{autodoc2-object} pynydus.api.protocols.Hatcher
```

All hatchers must implement `render(egg: Egg, output_dir: Path) -> RenderResult`.
The method produces target-platform files from the egg's structured modules.
Placeholders remain intact; secret injection happens after rendering.

Concrete implementations: `OpenClawHatcher`, `ZeroClawHatcher`, `LettaHatcher`.
