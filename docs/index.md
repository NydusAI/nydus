# PyNydus

**Portable state transport for AI agents.**

PyNydus packages agent state into a portable **Egg** artifact and moves it
between frameworks without manual migration. Secrets and PII are redacted
before packaging and restored on the other side.

- **Spawn** an Egg from an existing agent project (OpenClaw, ZeroClaw, or Letta)
- **Hatch** the Egg into any supported target runtime
- **Sign** Eggs with Ed25519 for integrity and share them via the **Nest** registry


## Core concepts

| Term | Meaning |
|------|---------|
| **Egg** | The portable artifact. In memory it is an `Egg` object (manifest + skills + memory + secrets). On disk it is a `.egg` ZIP archive. |
| **Spawn** | Read source files, redact secrets/PII, parse structure, and package into an Egg. |
| **Hatch** | Read an Egg, render target files, resolve secrets, and write to disk. |
| **Nydusfile** | A small DSL file declaring what to spawn: source type, redaction settings, and merge operations. |

```bash
pip install pynydus
```

```python
from pathlib import Path
from pynydus import Nydus

ny = Nydus()
egg = ny.spawn()                    # reads ./Nydusfile
ny.save(egg, Path("agent.egg"))     # portable .egg archive
result = ny.hatch(egg, target="letta", output_dir=Path("out"))
```


```{toctree}
:maxdepth: 2

getting-started/index
contributing/index
guides/index
design/index
api/index
```
