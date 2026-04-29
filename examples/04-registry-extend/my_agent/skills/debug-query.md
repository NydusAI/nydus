Diagnose slow or failing Snowflake queries using QUERY_HISTORY
and ACCESS_HISTORY views.

Steps:
1. Pull the query profile from INFORMATION_SCHEMA.QUERY_HISTORY
2. Identify spilling, partition pruning misses, and join explosions
3. Suggest fixes: clustering keys, materialization changes, or filter pushdown
4. Estimate cost savings from the proposed fix
