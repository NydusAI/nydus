# Client SDK

The {py:class}`~pynydus.client.client.Nydus` class is the main entry point for
using pynydus programmatically. It mirrors the CLI 1:1.

```python
from pynydus import Nydus

ny = Nydus()
egg = ny.spawn()  # reads ./Nydusfile
path = ny.pack(egg, output="agent.egg")

egg = ny.unpack(path)
egg.modules.skills      # list of SkillRecord
egg.modules.memory      # list of MemoryRecord
egg.inspect_secrets()

result = ny.hatch(egg, target="letta", secrets="agent.env")
```

## Nydus

```{autodoc2-object} pynydus.client.client.Nydus
```

See the full auto-generated reference with all method signatures:
{py:class}`pynydus.client.client.Nydus`
