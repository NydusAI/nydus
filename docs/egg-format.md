# The Egg Format

## Data model

An `Egg` has four parts, defined in {py:mod}`pynydus.api.schemas`:

**Manifest**: metadata including Nydus version, egg spec version (`"2.0"`),
creation timestamp, source type, which modules are included, redaction policy,
and an optional `sources` list with **at most one** entry (the SOURCE tree, if
any). Eggs with more than one manifest source entry are invalid for current
tooling.

**Skills** (`SkillsModule`): a list of `SkillRecord` entries (id, name, source
type, content, metadata) plus optional MCP server configurations.

**Memory** (`MemoryModule`): a list of `MemoryRecord` entries with labeled text.
Labels: `persona`, `flow`, `context`, `state`.

**Secrets** (`SecretsModule`): a list of `SecretRecord` entries. These are not
raw secret values. They are **placeholders** (`{{SECRET_001}}`, PII tokens) plus
metadata describing how real values are supplied at hatch time. Kinds:
`credential` (API keys extracted from config) and `pii` (detected by Presidio).

### Convenience accessors

```python
egg.skills.skills     # list[SkillRecord]
egg.memory.memory     # list[MemoryRecord]
egg.secrets.secrets   # list[SecretRecord]
```

## The `.egg` archive format

A packed Egg is a ZIP file with this layout:

```text
agent.egg
├── manifest.json           Manifest (versions, agent_type, redaction policy, ...)
├── memory.json             MemoryModule (list of labeled memory records)
├── secrets.json            SecretsModule (placeholders + injection metadata)
├── skills/
│   └── <slug>/
│       └── SKILL.md        Agent Skills format (YAML front matter + Markdown body)
├── nydus.json              Per-skill slug → {id, agent_type} mapping
├── mcp/
│   └── <server>.json       MCP server configs
├── raw/
│   └── ...                 Redacted source files (--passthrough hatch and auditing)
├── spawn_log.json          Pipeline log (redaction events, LLM calls, ...)
├── apm.yml                 APM compatibility manifest
├── signature.json          Optional Ed25519 signature
└── Nydusfile               Optional copy of the workspace Nydusfile (same text)
```

**Design rationale:** Memory and secrets use JSON for typed round-tripping via
Pydantic. Skills use the [Agent Skills](https://agentskills.io) Markdown format
for human readability and ecosystem compatibility. `nydus.json` bridges
Nydus-internal IDs to the skill slug directory names. `apm.yml` enables
compatibility with [APM](https://github.com/microsoft/apm). The `raw/` directory
is optional provenance, not the canonical model.

Archive layout constants are defined in `pynydus.engine.packager`
(`MANIFEST_ENTRY`, `MEMORY_ENTRY`, `SECRETS_ENTRY`, etc.) as a single source of
truth.

## API reference

See {doc}`api/schemas` for the full auto-generated Pydantic model reference.
