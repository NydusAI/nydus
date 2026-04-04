# Client SDK

The {py:class}`~pynydus.client.client.Nydus` class is the main entry point for
using PyNydus programmatically. It mirrors the CLI 1:1.

**Hatch modes:** {py:meth}`~pynydus.client.client.Nydus.hatch` defaults to
`mode="rebuild"` (regenerate files from structured egg modules). Use
`mode="passthrough"` to replay the redacted `raw/` snapshot; use non-empty
`egg.raw_artifacts` (for example from {py:meth}`~pynydus.client.client.Nydus.load`
or after spawn). If you used {py:meth}`~pynydus.client.client.Nydus.load` with
`include_raw=False`, `egg.raw_artifacts` is empty — pass `raw_artifacts=` from
{py:func}`pynydus.engine.packager.read_raw_artifacts` (for example
`read_raw_artifacts(path)`), or reload with `include_raw=True`. {py:meth}`~pynydus.client.client.Nydus.hatch` defaults
`raw_artifacts` and `spawn_log` from the egg when omitted.

## Example

```python
from pathlib import Path
from pynydus import Nydus

ny = Nydus()  # reads NYDUS_* environment variables; see :doc:`../configuration`

# Spawn
egg = ny.spawn()                         # reads ./Nydusfile
egg = ny.spawn(nydusfile="other/Nydusfile")

# Save / load
path = ny.save(egg, Path("agent.egg"))
path = ny.save(egg, Path("agent.egg"), sign=True)

# Load and inspect (includes raw/ and spawn log)
egg = ny.load(Path("agent.egg"))
egg.skills.skills       # list of SkillRecord
egg.memory.memory       # list of MemoryRecord
egg.inspect_secrets()
report = ny.validate(egg)
diff = ny.diff(egg_a, egg_b)

# Hatch
result = ny.hatch(
    egg,
    target="letta",
    output_dir=Path("out"),
    secrets="agent.env",
    mode="rebuild",            # default; use mode="passthrough" to replay raw/
    raw_artifacts=raw,         # optional; defaults to egg.raw_artifacts
    spawn_log=spawn_log,       # optional; defaults to egg.spawn_log
)
print(result.output_dir, result.files_created, result.warnings)

# Or load then hatch (same as CLI)
egg = ny.load(Path("agent.egg"))
result = ny.hatch(egg, target="openclaw", output_dir=Path("out"))
```

**Notes:**

- `spawn()` fills **`egg.raw_artifacts`** and **`egg.spawn_log`**; **`save()`**
  writes them to the archive by default.
- `load(..., include_raw=False)` leaves **`egg.raw_artifacts`** empty; use **`read_raw_artifacts`**
  or full **`load()`** when passthrough needs **`raw/`**.
- `hatch()` defaults to **rebuild**. For **passthrough**, **`egg.raw_artifacts`**
  must be non-empty (e.g. from **`load()`** or spawn), or pass **`raw_artifacts=`** explicitly.
- Configure LLM and registry via environment variables (`NYDUS_LLM_TYPE`,
  `NYDUS_LLM_API_KEY`, `NYDUS_REGISTRY_URL`, …); see {doc}`../configuration`.

## Nydus

```{autodoc2-object} pynydus.client.client.Nydus
```

See the full auto-generated reference with all method signatures:
{py:class}`pynydus.client.client.Nydus`
