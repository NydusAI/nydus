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

## API reference


See {doc}`/reference/api/schemas` for the full Pydantic model reference.
