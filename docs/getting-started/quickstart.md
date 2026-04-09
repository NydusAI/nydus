# Quickstart

Get from zero to a hatched agent in five steps. Assumes you have
{doc}`installed PyNydus and gitleaks <install>`.

## 1. Write a Nydusfile


Create a `Nydusfile` in your project directory:

```text
SOURCE openclaw ./my-agent/
REDACT true
```

See {doc}`/guides/nydusfile` for the full DSL reference.

## 2. Spawn an Egg


**CLI:**

```bash
nydus spawn -o agent.egg
```

**Python SDK:**

```python
from pathlib import Path
from pynydus import Nydus

ny = Nydus()
egg = ny.spawn()  # reads ./Nydusfile
ny.save(egg, Path("agent.egg"))
```

## 3. Inspect


```bash
nydus inspect agent.egg --secrets --logs
```

## 4. Hatch into another runtime


During spawn, real secrets and PII were replaced with placeholders like
`{{SECRET_001}}`. Before hatching, generate a template listing the secrets
the Egg needs, fill in real values, then hatch:

```bash
nydus env agent.egg -o agent.env
# edit agent.env with real values
nydus hatch agent.egg --target letta --secrets agent.env
```


Or with the Python SDK:

```python
from pynydus.common.enums import AgentType

result = ny.hatch(egg, target=AgentType.LETTA, secrets="agent.env")
print(result.files_created)
```

## 5. Share via Nest


```bash
nydus login myuser
nydus push agent.egg --name myuser/my-agent --version 0.1.0
```


Pull from another machine:

```bash
nydus pull myuser/my-agent --version 0.1.0 -o agent.egg
```

## Next steps


- {doc}`/guides/nydusfile`: control what gets spawned
- {doc}`/guides/security`: how secrets and PII are protected
- {doc}`/api/cli`: full CLI reference
- {doc}`/guides/configuration`: environment variables
