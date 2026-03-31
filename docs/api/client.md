# Client SDK

The `Nydus` class is the main entry point for using pynydus programmatically.
It mirrors the CLI commands one-to-one: `spawn()`, `hatch()`, `pack()`,
`unpack()`, `inspect()`, `validate()`, `diff()`, `push()`, `pull()`, and more.

## Basic usage

```python
from pynydus import Nydus

ny = Nydus()

# Spawn from a Nydusfile in the current directory
egg = ny.spawn()

# Pack the in-memory Egg into a .egg archive on disk
path = ny.pack(egg, output="agent.egg")

# Unpack an archive back into an in-memory Egg
egg = ny.unpack("agent.egg")

# Inspect modules
print(len(egg.modules.skills))    # number of skills
print(len(egg.modules.memory))    # number of memory records
egg.inspect_secrets()              # print secret placeholders

# Hatch into a target framework
result = ny.hatch(egg, target="letta", secrets="agent.env")
print(result.output_dir)
print(result.files_created)
```

## Signing

```python
# Sign during pack (requires private key at ~/.nydus/keys/private.pem)
ny.pack(egg, output="signed.egg", sign=True)
```

## Registry operations

```python
# Push to Nest
ny.push("agent.egg", name="myuser/my-agent", version="0.1.0")

# Pull from Nest
path = ny.pull("myuser/my-agent", version="0.1.0", output="agent.egg")

# List versions
versions = ny.list_versions("myuser/my-agent")
```

## Diff

```python
report = ny.diff("v1.egg", "v2.egg")
for entry in report.entries:
    print(entry.change, entry.module, entry.id)
```

## API reference

```{autodoc2-object} pynydus.client.client.Nydus
```
