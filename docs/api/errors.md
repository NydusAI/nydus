# Errors

All pynydus exceptions inherit from `NydusError`. Import them from
`pynydus.api.errors`.

```python
from pynydus.api.errors import NydusError, NydusfileError, EggError
```

## Exception hierarchy

### NydusError

Base error for all Nydus operations. Catch this to handle any pynydus
exception generically.

### NydusfileError

Raised when the Nydusfile cannot be parsed or fails static validation. Has a
`line` attribute indicating the source line number where the error occurred.

```python
try:
    egg = ny.spawn()
except NydusfileError as e:
    print(f"Line {e.line}: {e}")
```

### ConnectorError

Raised when a spawner or hatcher encounters an error. Common causes: unknown
source type, unreadable input directory, missing required files for detection.

### EggError

Raised when reading, writing, or packaging an Egg fails. Common causes:
corrupted ZIP archive, missing required modules (`memory.json`, `manifest.json`),
or structural inconsistencies.

### HatchError

Raised during the hatching pipeline. Common causes: missing required secrets
in the `.env` file, Egg version incompatibility, or target rendering failures.

### ConfigError

Raised when the Nydus configuration is invalid. Common causes: missing
registry URL in `config.json`, invalid LLM configuration, or missing keys.

### RegistryError

Raised when communicating with the Nest registry fails. Common causes: HTTP
errors, authentication failures, SHA-256 checksum mismatches on pulled Eggs,
or duplicate name:version conflicts on push (409).

## Handling errors

A typical pattern for CLI-style error handling:

```python
from pynydus import Nydus
from pynydus.api.errors import NydusfileError, EggError, HatchError

ny = Nydus()

try:
    egg = ny.spawn()
    ny.pack(egg, output="agent.egg")
except NydusfileError as e:
    print(f"Nydusfile error on line {e.line}: {e}")
except EggError as e:
    print(f"Packaging error: {e}")

try:
    result = ny.hatch(egg, target="letta", secrets="agent.env")
except HatchError as e:
    print(f"Hatch failed: {e}")
```
