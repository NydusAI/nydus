# Nydus (portable state transport for AI agents)

Use this skill when you want to **snapshot your own state** (spawn an egg),
**restore from a snapshot** (hatch an egg), or **migrate your state** to a
different agent framework.

## When to use

- You want a portable copy of yourself: persona, skills, memory, MCP configs,
  and secrets, packaged into a single `.egg` archive.
- You want to restore yourself (or a different agent) from an existing `.egg`.
- You want to publish or download eggs from a hosted registry.

## Install

```bash
pip install pynydus
```

For spawning with redaction (the default), **gitleaks** must be on `PATH`:

```bash
# macOS
brew install gitleaks

# Linux
curl -sSL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_8.21.2_linux_x64.tar.gz \
  | tar xz -C /usr/local/bin gitleaks
```

Hatching does not require gitleaks.

## Spawn (create an egg of yourself)

1. Collect your state files into a directory. At minimum, include persona/identity
   markdown and any skills, MCP configs, or memory files you want preserved.

2. Pick the agent type whose file layout is closest to yours (see
   **File layout by type** below).

3. Create a `Nydusfile` in that directory:

```
SOURCE openclaw ./
REDACT true
```

4. Run the spawn:

```bash
nydus spawn -o me.egg
```

5. Optionally push to the Nest registry:

```bash
nydus push me.egg -n namespace/my-agent -v 1.0.0
```

### Disabling redaction

Set `REDACT false` in the Nydusfile to skip secret scanning and PII redaction.
This removes the gitleaks requirement but means real credentials may end up in
the egg.

## Hatch (restore from an egg)

```bash
nydus hatch agent.egg -t openclaw -o ./output
```

If the egg contains secrets, generate a template and fill it in:

```bash
nydus env agent.egg -o hatch.env
# edit hatch.env with real values
nydus hatch agent.egg -t openclaw -s hatch.env -o ./output
```

Use `-P` (passthrough) to replay the original redacted files verbatim instead
of rebuilding from modules. Use `-S` to skip validation.

## File layout by type

### openclaw (markdown-based agents)

Best fit for agents whose state is mostly markdown files.

| File | Maps to |
|------|---------|
| `SOUL.md`, `IDENTITY.md` | persona memory |
| `AGENTS.md`, `BOOT.md` | flow memory |
| `USER.md`, `TOOLS.md` | context memory |
| `knowledge.md`, `MEMORY.md` | state memory |
| `memory/*.md` | state memory (timestamped) |
| `skill.md`, `skills.md`, `skills/*.md` | skills |
| `mcp.json` | MCP server configs |
| `config.json` | agent config |
| `apm.yml` | APM manifest (passthrough) |

### letta (AgentFile-based agents)

Best fit for agents using `.af` AgentFile format or `agent_state.json`.

| File | Maps to |
|------|---------|
| `*.af` | full agent state (blocks, tools, MCP) |
| `agent_state.json` | fallback agent state |
| `tools/*.py` | skills |
| `archival/*.txt`, `archival/*.md` | state memory |
| `.letta/*.json` | Letta config |

### zeroclaw (toml-config agents)

Best fit for agents using `config.toml` and Python tool files.

| File | Maps to |
|------|---------|
| `persona.md`, `identity.json` | persona memory |
| `AGENTS.md`, `SOUL.md` | flow/persona memory |
| `USER.md` | context memory |
| `tools/*.py`, `tools.json` | skills |
| `memory/*.md` | state memory |
| `config.toml` | agent config (name, description, LLM model) |
| `mcp.json` | MCP server configs |

## Nydusfile reference

```
FROM base/openclaw:0.0.1       # optional base egg (local path or registry ref)
SOURCE openclaw ./              # agent type + source directory
REDACT true                     # secret scan + PII redaction (default true)
LABEL memory/*.md state         # override memory label by glob pattern
EXCLUDE state                   # drop a memory label from the egg
REMOVE file drafts/*            # drop source files before parsing
ADD skill ./new-skill.md        # merge op (requires FROM)
SET memory persona ./persona.md # merge op (requires FROM)
```

Only one `SOURCE` line is allowed. `ADD`, `SET`, and `REMOVE` (merge ops)
require a `FROM` base egg.

## CLI quick reference

| Command | What it does |
|---------|-------------|
| `nydus spawn -o out.egg` | Create egg from Nydusfile in current directory |
| `nydus hatch egg -t TYPE -o DIR` | Deploy egg into target runtime |
| `nydus inspect egg` | Print egg summary with validation |
| `nydus env egg -o .env` | Generate secret template from egg |
| `nydus extract all -f egg -o DIR` | Extract all standard artifacts |
| `nydus diff a.egg b.egg` | Compare two eggs |
| `nydus push egg -n NAME -v VER` | Publish egg to Nest registry |
| `nydus pull NAME -v VER -o out.egg` | Download egg from Nest registry |
| `nydus keygen` | Generate Ed25519 signing keypair |

## Registry (Nest)

Nest is the hosted egg registry at `https://nest.nydus.ag`.
For the full registry API, fetch `GET /skill.md` from the Nest server
or see the [nest skill file](../nest/backend/nest/skill.md).

## More information

- Full documentation: https://pynydus.readthedocs.io/en/latest/
- Repository: https://github.com/NydusAI/nydus
- PyPI: https://pypi.org/project/pynydus/
