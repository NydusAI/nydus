Summarize long Snowflake query results, dbt run logs, or data quality
reports into concise bullet points.

Rules:
1. Lead with the conclusion: pass/fail, row count delta, cost.
2. Group issues by severity: critical → warning → info.
3. Include the specific table or model name in every bullet.
4. If the output exceeds 20 rows, summarize the top 5 and note the total.
