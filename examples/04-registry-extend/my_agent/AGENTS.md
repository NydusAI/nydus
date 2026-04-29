# Session Startup

1. Read SOUL.md
2. Read USER.md
3. Read today + yesterday from memory/
4. Read MEMORY.md

# Data Pipeline Workflow

1. When asked to build a pipeline, confirm source → staging → mart flow.
2. Always include: freshness SLA, clustering keys, and cost estimate.
3. After building, generate a dbt test YAML alongside the model.

# Escalation

- Schema changes affecting downstream consumers: alert before applying.
- Warehouse credit spikes > 2x baseline: flag immediately.
- Production incidents: triage first, root-cause after stabilization.
