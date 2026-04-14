# APM (Agent Package Manager) Spec

Spec version: 0.1
Source: https://microsoft.github.io/apm/

## Overview

The Agent Package Manager (APM) is a Microsoft initiative for discovering,
distributing, and managing AI agent packages. Agents declare their metadata,
dependencies, and capabilities in an `apm.yml` manifest file.

## Nydus Conventions

Nydus treats APM as a **pure passthrough**:

1. **Spawn**: if the source project contains `apm.yml`, copy it verbatim
   into the egg at the archive root.
2. **Hatch**: if the egg contains `apm.yml`, write it to the output
   directory.
3. **Extract**: `nydus extract apm --from agent.egg` extracts the file,
   or reports "no apm.yml in this egg."
4. **No parsing, no validation, no generation.** Nydus does not interpret
   `apm.yml` content. The file is opaque binary cargo.

This approach ensures that agents with APM manifests retain them through
Nydus spawn/hatch cycles without any lossy transformation.

## APM Manifest Reference

For reference, an `apm.yml` file typically contains:

```yaml
name: my-agent
version: 1.0.0
description: An AI agent that helps with booking
author: Example Corp
license: MIT
runtime:
  language: python
  version: ">=3.10"
dependencies:
  - name: openai
    version: ">=1.0"
capabilities:
  - text-generation
  - tool-use
endpoints:
  - protocol: a2a
    url: https://api.example.com/agent
```

Refer to the [APM specification](https://microsoft.github.io/apm/) for the
authoritative format and field definitions.

## Validation Schema

No validation schema is provided. Nydus does not validate `apm.yml` content.
