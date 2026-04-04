# Nest Registry

Nest is the registry service for publishing and pulling Eggs, analogous to
Docker Hub for container images.

## Authentication

```bash
nydus register myuser
nydus login myuser
```

Credentials (JWT tokens) are stored at `~/.nydus/credentials.json`.
Log out: `nydus logout`.

## Push

```bash
nydus push agent.egg --name myuser/my-agent --version 0.1.0
```

Duplicate `name:version` pairs are rejected (409 Conflict).

## Pull

```bash
nydus pull myuser/my-agent --version 0.1.0 -o agent.egg
```

Downloads are verified against the server's SHA-256 checksum.

## Nydusfile integration

The FROM directive can reference registry Eggs:

```text
FROM nydus/openclaw:0.3.0
```

Registry references (`name:version`) are pulled from the configured Nest
server. Local paths (e.g. `FROM ./base.egg`) resolve relative to the
Nydusfile directory.

## SDK usage

```python
from pynydus import Nydus

ny = Nydus()
ny.push("agent.egg", name="myuser/my-agent", version="0.1.0")
path = ny.pull("myuser/my-agent", version="0.1.0", output="agent.egg")
versions = ny.list_versions("myuser/my-agent")
```

## Configuration

Set **`NYDUS_REGISTRY_URL`** (required for push/pull) and optionally
**`NYDUS_REGISTRY_AUTHOR`**. See {doc}`configuration`.
