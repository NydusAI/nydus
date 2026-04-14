# Client SDK

The {py:class}`~pynydus.client.client.Nydus` class is the main entry point for
using PyNydus programmatically. It mirrors CLI behavior, but Typer entry points
call the same engines directly rather than delegating to this class.

## Example


```python
from pathlib import Path
from pynydus import Nydus

ny = Nydus()

# Spawn
egg = ny.spawn()                         # reads ./Nydusfile
egg = ny.spawn(nydusfile="other/Nydusfile")

# Save / load
path = ny.save(egg, Path("agent.egg"))
path = ny.save(egg, Path("agent.egg"), sign=True)

# Load and inspect (includes raw/ and spawn log)
egg = ny.load(Path("agent.egg"))
egg.skills.skills       # list of AgentSkill
egg.mcp.configs         # dict of MCP server configs
egg.memory.memory       # list of MemoryRecord
egg.inspect_secrets()
report = ny.validate(egg)
diff = ny.diff(egg_a, egg_b)

# Hatch (rebuild mode, the default)
result = ny.hatch(
    egg,
    target="letta",
    output_dir=Path("out"),
    secrets="agent.env",
)
print(result.output_dir, result.files_created, result.warnings)
```


**Notes:**

- `spawn()` fills `egg.raw_artifacts` and `egg.spawn_log`. `save()` writes
  them to the archive by default.
- `hatch()` defaults to **rebuild** mode (regenerate files from structured Egg
  modules). Set `mode="passthrough"` to replay the redacted `raw/` snapshot
  verbatim. Passthrough requires `egg.raw_artifacts` to be non-empty, which
  it is after `spawn()` or `load()` with the default `include_raw=True`.
- If you loaded with `load(..., include_raw=False)`, `raw_artifacts` is empty.
  Either reload with `include_raw=True` or pass `raw_artifacts=` from
  `pynydus.engine.packager.read_raw_artifacts(path)`.
- Configure LLM and registry via environment variables (`NYDUS_LLM_TYPE`,
  `NYDUS_LLM_API_KEY`, `NYDUS_REGISTRY_URL`, etc.). See {doc}`/guides/configuration`.
- Registry `pull()` defaults `version` to `"latest"` if omitted. The `nydus pull`
  CLI still requires `--version`. See {doc}`/guides/nest-registry`.

## Nydus


```{autodoc2-object} pynydus.client.client.Nydus
```

See the full auto-generated reference with all method signatures:
{py:class}`pynydus.client.client.Nydus`
