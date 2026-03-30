# pynydus

**Portable state transport for AI agents.**

Nydus is a portable packaging layer for AI agents. Named after the Zerg Nydus
Network from StarCraft (a transport tunnel that moves units instantly between
any two locations), Nydus transports agent state between frameworks without
manual migration.

```bash
pip install pynydus
```

```
Source → Spawn → Egg → Hatch → Target
```

## How it works

Nydus defines a portable artifact called an **Egg** and bidirectional connectors
for encoding (**spawning**) and decoding (**hatching**) agent state:

- **Spawn**: read source agent artifacts, extract skills/memory/secrets, package into an Egg
- **Hatch**: decode an Egg into any supported target runtime, resolving secrets from a `.env` file
- **Share**: push/pull Eggs through the Nest registry

The Egg stores three modules with deterministic placeholder linking: every
redacted PII value or secret maps to a unique token with tracked occurrences.
Users re-personalize via a `.env` file at hatch time.

## Contents

```{toctree}
:maxdepth: 2

quickstart
cli
nydusfile
api/index
advanced/index
```
