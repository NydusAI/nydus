# Nest Registry

Nest is the registry service for publishing and pulling Eggs, analogous to
Docker Hub for container images or npm for JavaScript packages.

## Authentication

Register an account and log in before pushing:

```bash
nydus register myuser
nydus login myuser
```

Credentials (JWT tokens) are stored at `~/.nydus/credentials.json` and
automatically included in subsequent push/pull requests.

Log out to remove stored credentials:

```bash
nydus logout
```

## Publishing an Egg

Push a local Egg to the registry with a name and version:

```bash
nydus push agent.egg --name myuser/my-agent --version 0.1.0
```

The Egg is uploaded with its SHA-256 checksum recorded server-side. Duplicate
`name:version` pairs are rejected (409 Conflict). Increment the version for
each new release.

## Pulling an Egg

Download an Egg from the registry:

```bash
nydus pull myuser/my-agent --version 0.1.0 -o agent.egg
```

The downloaded file is verified against the server's SHA-256 checksum. If the
hashes do not match, the file is deleted and an error is raised.

## Listing versions

Use the SDK to list all published versions of an Egg:

```python
from pynydus import Nydus

ny = Nydus()
versions = ny.list_versions("myuser/my-agent")
for v in versions:
    print(v["version"], v["created_at"], v["size"])
```

Each entry contains: `name`, `version`, `sha256`, `size`, `author`, and
`created_at`.

## Configuration

The registry URL is configured in `config.json`:

```json
{
  "registry": {
    "url": "https://nest.nydus.tech",
    "author": "myuser"
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `url` | Yes | Nest registry endpoint |
| `author` | No | Default author name for pushes |

## Nydusfile integration

The `FROM` directive can reference Eggs in the registry by name and version:

```text
FROM nydus/openclaw:0.2.0
```

During spawning, the pipeline resolves registry references (`name:version`
format) by pulling from the configured Nest endpoint. Local file paths
(e.g., `FROM ./base.egg`) are resolved relative to the Nydusfile directory.

## SDK usage

```python
from pynydus import Nydus

ny = Nydus()

# Push
ny.push("agent.egg", name="myuser/my-agent", version="0.1.0")

# Pull
path = ny.pull("myuser/my-agent", version="0.1.0", output="agent.egg")

# List versions
versions = ny.list_versions("myuser/my-agent")
```
