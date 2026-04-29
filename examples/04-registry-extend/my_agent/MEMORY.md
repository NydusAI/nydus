# Long-term Notes

- Team uses dbt 1.8 with Snowflake adapter.
- Primary warehouse: ANALYTICS_WH (X-Small, auto-suspend 60s).
- Naming convention: raw_*, stg_*, int_*, mart_*.
- Daily refresh window: 02:00–04:00 UTC.
