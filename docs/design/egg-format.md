# The Egg Format

## Data model


An `Egg` has four modules, defined in {py:mod}`pynydus.api.schemas`:

| Module | Class | Contents |
|--------|-------|----------|
| **Manifest** | `Manifest` | Nydus version, egg spec version (`"2.0"`), timestamp, source type, included modules, redaction policy, optional signature |
| **Skills** | `SkillsModule` | List of `SkillRecord` (id, name, content) plus optional MCP server configurations |
| **Memory** | `MemoryModule` | List of `MemoryRecord`, each labeled Memory[**persona**], Memory[**flow**], Memory[**context**], or Memory[**state**] |
| **Secrets** | `SecretsModule` | List of `SecretRecord` placeholders (`{{SECRET_001}}`, `{{PII_001}}`) with injection metadata |


```python
egg.skills.skills     # list[SkillRecord]
egg.memory.memory     # list[MemoryRecord]
egg.secrets.secrets   # list[SecretRecord]
```

## The `.egg` archive format


A packed Egg is a ZIP file:

```text
agent.egg
├── manifest.json       Manifest metadata
├── memory.json         Memory records (labeled)
├── secrets.json        Secret/PII placeholders + injection metadata
├── skills/
│   └── <slug>/
│       └── SKILL.md    Skill content (YAML front matter + Markdown)
├── nydus.json          Skill slug to {id, agent_type} mapping
├── mcp/
│   └── <server>.json   MCP server configs
├── raw/
│   └── ...             Redacted source files (for passthrough hatch)
├── spawn_log.json      Pipeline event log
├── apm.yml             APM compatibility manifest
├── signature.json      Ed25519 signature (optional)
└── Nydusfile           Copy of the workspace Nydusfile
```


Skills use the [Agent Skills](https://agentskills.io) Markdown format for
human readability. `apm.yml` enables
[APM](https://github.com/microsoft/apm) compatibility. `raw/` is optional
provenance used for passthrough hatching, not the canonical model.

## Manifest fields


`manifest.json` contains top-level Egg metadata:

| Field | Type | Description |
|-------|------|-------------|
| `nydus_version` | string | PyNydus version that created this Egg |
| `min_nydus_version` | string | Minimum PyNydus version required to open this Egg (default `"0.1.0"`) |
| `egg_version` | string | Egg format spec version (`"2.0"`) |
| `created_at` | ISO 8601 | Timestamp of Egg creation |
| `agent_type` | string | Source platform (`openclaw`, `letta`, `zeroclaw`) |
| `included_modules` | list | Which modules are populated (`["skill", "memory", "secret"]`) |
| `signature` | string | Ed25519 signature (empty if unsigned) |
| `base_egg` | string or null | `FROM` reference (registry qualifier or local path, e.g. `"nydus/openclaw:0.3.0"` or `"./base.egg"`) |
| `redaction_policy` | object | `{pii_redacted: bool, secrets_placeholder_only: bool}` |
| `source_metadata` | object | Platform-specific metadata from the spawner (e.g., agent name, model) |
| `sources` | list | At most one `{agent_type, source_path}` entry |

## Memory record schema


Each entry in `memory.json` is a `MemoryRecord`:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable ID (`mem_001`, `mem_002`, ...) |
| `text` | string | Record content (with placeholders, not real secrets) |
| `label` | string | One of `persona`, `flow`, `context`, `state` |
| `agent_type` | string | Source platform that produced this record |
| `source_store` | string | Original source file (e.g., `SOUL.md`, `memory/2026-04-01.md`) |
| `skill_ref` | string or null | Associated skill ID (if this memory relates to a skill) |
| `timestamp` | ISO 8601 or null | When this memory was created or last updated |
| `shareable` | bool | Whether this record can be shared (default `true`) |
| `metadata` | object | Additional key-value metadata |

Example:

```json
{
  "id": "mem_001",
  "text": "I am a travel planning assistant. My name is {{PII_001}}.",
  "label": "persona",
  "agent_type": "openclaw",
  "source_store": "SOUL.md",
  "skill_ref": null,
  "timestamp": null,
  "shareable": true,
  "metadata": {"source_file": "SOUL.md"}
}
```

## Secret record schema


Each entry in `secrets.json` is a `SecretRecord`:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable ID (`secret_001`, `pii_001`, ...) |
| `placeholder` | string | The token in file content (`{{SECRET_001}}`, `{{PII_001}}`) |
| `kind` | string | `credential` (gitleaks) or `pii` (Presidio) |
| `pii_type` | string or null | Entity type for PII records (e.g., `PERSON`, `EMAIL_ADDRESS`) |
| `name` | string | Human-readable name used as `.env` key (e.g., `AWS_ACCESS_KEY_ID`) |
| `required_at_hatch` | bool | If `true`, hatch fails without this secret |
| `injection_mode` | string | How the value is substituted (`env`) |
| `description` | string | What was redacted |
| `value_present` | bool | Always `false` in the Egg (real values are never stored) |
| `occurrences` | list | Source files containing this placeholder |

Example:

```json
{
  "id": "secret_001",
  "placeholder": "{{SECRET_001}}",
  "kind": "credential",
  "pii_type": null,
  "name": "AWS_ACCESS_KEY_ID",
  "required_at_hatch": false,
  "injection_mode": "env",
  "description": "",
  "value_present": false,
  "occurrences": ["config.json"]
}
```

## raw/ directory


The `raw/` directory in the archive contains the redacted source files as
they appeared after Step 3 of the spawn pipeline (post-redaction, pre-parsing).
All real secrets and PII have been replaced with placeholders.

This directory is used for **passthrough hatching**, where the original file
structure is replayed verbatim instead of being regenerated from structured
modules.

`raw/` is populated during `spawn()` and written during `save()`. When loading
an Egg with `load(path, include_raw=False)`, this directory is skipped for
faster loading.

## API reference


See {doc}`/api/python/schemas` for the full Pydantic model reference.
