# 04 Registry Extend: All Directives

Pulls a base egg from the Nest registry and exercises every Nydusfile
directive: FROM, SOURCE, REDACT, ADD, REMOVE, EXCLUDE, LABEL, and a
user-defined secret.

## Prerequisites

- `pynydus` installed (`uv pip install -e .` from repo root)
- gitleaks v8+ (REDACT true triggers secret scanning)
- spaCy model: `python -m spacy download en_core_web_lg`
- `NYDUS_REGISTRY_URL` set (e.g. `http://localhost:8000` or your Nest instance)
- The base egg `admin/openclaw:0.0.1` published in the registry

## Run

```bash
export NYDUS_REGISTRY_URL=http://localhost:8000
nydus spawn -o agent.egg
nydus inspect agent.egg
```

## What to look for

- `FROM admin/openclaw:0.0.1` pulls the base egg from the registry
- `ADD skill` layers on `custom_summarizer/summarizer.md`
- `ADD memory.label=context` and `ADD memory.label=persona` add new records
- `ADD secret SNOWFLAKE_API_KEY` registers a secret placeholder
- `REMOVE skill outdated_workflow` drops a skill from the base egg
- `REMOVE file *.log` filters `debug.log` from the source tree before parsing
- `LABEL MEMORY.md context` reclassifies MEMORY.md records from `state` to `context`, saving them from EXCLUDE
- `EXCLUDE state` drops all remaining state-labeled memory from the final egg
