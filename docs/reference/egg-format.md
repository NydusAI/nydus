# The Egg Format

## Data model

An `Egg` has four parts, defined in {py:mod}`pynydus.api.schemas`:

**Manifest**: metadata including Nydus version, egg spec version (`"2.0"`), timestamp,
source type, included modules, redaction policy, and an optional `sources` list
(at most one entry).

**Skills** (`SkillsModule`): list of `SkillRecord` entries (id, name, source
type, content, metadata) plus optional MCP server configurations.

**Memory** (`MemoryModule`): list of `MemoryRecord` entries with labeled text.
Labels: `persona`, `flow`, `context`, `state`.

**Secrets** (`SecretsModule`): list of `SecretRecord` entries. These are **placeholders**
(`{{SECRET_001}}`, PII tokens) with metadata describing how real values are
supplied at hatch time. Kinds: `credential` and `pii`.

### Convenience accessors

```python
egg.skills.skills     # list[SkillRecord]
egg.memory.memory     # list[MemoryRecord]
egg.secrets.secrets   # list[SecretRecord]
```

## The `.egg` archive format

A packed Egg is a ZIP file:

```text
agent.egg
├── manifest.json           Manifest
├── memory.json             MemoryModule
├── secrets.json            SecretsModule (placeholders + injection metadata)
├── skills/
│   └── <slug>/
│       └── SKILL.md        Agent Skills format (YAML front matter + Markdown)
├── nydus.json              Per-skill slug → {id, agent_type} mapping
├── mcp/
│   └── <server>.json       MCP server configs
├── raw/
│   └── ...                 Redacted source files (passthrough hatch + auditing)
├── spawn_log.json          Pipeline log
├── apm.yml                 APM compatibility manifest
├── signature.json          Optional Ed25519 signature
└── Nydusfile               Copy of the workspace Nydusfile
```

Memory and secrets use JSON for typed round-tripping via Pydantic. Skills use
the [Agent Skills](https://agentskills.io) Markdown format for human
readability. `nydus.json` bridges internal IDs to skill slug directories.
`apm.yml` enables [APM](https://github.com/microsoft/apm) compatibility.
`raw/` is optional provenance, not the canonical model.

## API reference

See {doc}`api/schemas` for the full Pydantic model reference.
