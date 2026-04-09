# OpenClaw Workspace Specification

An OpenClaw agent workspace is a directory of markdown and config files
that define the agent's persona, operating instructions, user context,
accumulated memory, and skills.

## Bootstrap Files (loaded every session)

| File | Purpose |
|------|---------|
| SOUL.md | Persona, tone, boundaries. Short and opinionated — personality directives, not a biography. Defines the agent's voice and behavioral style. |
| IDENTITY.md | Structured profile: Name, Creature, Vibe, Emoji, Avatar. Created during first-run bootstrap. Uses `- **Field:** value` format. |
| AGENTS.md | Operating instructions, priorities, behavioral rules. Always starts with the session startup protocol (read SOUL.md, USER.md, memory/, MEMORY.md). The "how to work" file. |
| USER.md | Who the user is: name, timezone, preferences, how to address them. The handler's profile. |
| TOOLS.md | Environment-specific local notes — API endpoints, rate limits, device names, SSH hosts. Does not define tool capabilities (skills do that). |

## Memory Files

| File | Purpose |
|------|---------|
| HEARTBEAT.md | Optional tiny checklist for heartbeat runs. Keep short or empty to skip heartbeat API calls. |
| MEMORY.md | Curated long-term memory. Only loaded in main/private sessions (security-sensitive — never in shared/group contexts). Lightweight index, not a data dump. |
| memory/YYYY-MM-DD.md | Daily memory log, one file per day. Raw logs of what happened. Read today + yesterday on session start. |

## Skills

| File | Purpose |
|------|---------|
| skills/*.md | One skill per file, named descriptively in kebab-case. Highest-precedence skill location. |

Legacy: `skill.md` or `skills.md` as a single file with `# Name`
sections is recognized but not recommended.

## Configuration

| File | Purpose |
|------|---------|
| config.json / config.yaml | Non-secret configuration. Commonly misused to store API keys (a mistake the security pipeline catches). |
| mcp.json / mcp/*.json | MCP server configurations. |

## First-Run Files (deleted after setup)

| File | Purpose |
|------|---------|
| BOOTSTRAP.md | First-run onboarding script. Agent follows it, fills in IDENTITY.md and USER.md, then deletes it. |
| BOOT.md | Startup hook instructions (requires `hooks.internal.enabled`). |

## Conventions

- Bootstrap filenames are UPPERCASE (SOUL.md, AGENTS.md, USER.md, IDENTITY.md, TOOLS.md).
- SOUL.md should be concise: personality directives, not prose. "Short beats long. Sharp beats vague."
- AGENTS.md must start with the session startup protocol. It's the SOP for the agent.
- IDENTITY.md uses structured fields: `- **Name:**`, `- **Creature:**`, `- **Vibe:**`, `- **Emoji:**`, `- **Avatar:**`.
- USER.md is for user identity, timezone, and preferences. PII (name, email, phone) belongs here, not in SOUL.md.
- TOOLS.md is for environment-specific notes (API endpoints, device names, rate limits), not tool definitions.
- Credentials belong outside the workspace (~/.openclaw/agents/). API keys in workspace config files are an anti-pattern.
- memory/ entries accumulate daily. Older entries can be pruned or compacted.
- MEMORY.md is security-sensitive — only loaded in main sessions, never in group/shared contexts.
- skills/ files are standalone — each should be self-contained.
