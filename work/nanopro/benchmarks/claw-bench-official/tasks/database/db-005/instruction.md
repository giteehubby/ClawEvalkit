# Task: Query Optimization

You are given a database schema and three slow SQL queries that perform full table scans.

## Input Files

- `workspace/schema.sql` — table definitions for a large e-commerce database
- `workspace/slow_queries.sql` — three unoptimized queries with performance issues

## Goal

Optimize the queries and recommend indexes to improve performance.

## Requirements

1. Read both input files carefully.
2. Rewrite each of the 3 queries to be more efficient. Save as `workspace/optimized_queries.sql`.
   - Each query must be separated by a comment line: `-- Query 1`, `-- Query 2`, `-- Query 3`
   - Optimized queries MUST produce the **same results** as the originals.
3. Create `workspace/index_recommendations.json` with recommended indexes:
   ```json
   [
     {
       "table": "table_name",
       "columns": ["col1", "col2"],
       "reason": "Brief explanation"
     }
   ]
   ```
4. Recommend at least 3 indexes, each referencing valid tables and columns from the schema.

## Optimization Hints

- Query 1: Uses a function on an indexed column in WHERE clause, preventing index usage.
- Query 2: Uses `SELECT *` with a subquery that could be a JOIN, plus missing composite index.
- Query 3: Uses `OR` conditions that prevent index usage, plus unnecessary DISTINCT.

## Notes

- Use SQLite-compatible SQL syntax.
- The optimized queries must be syntactically valid and produce identical results.
- Focus on eliminating full table scans, reducing unnecessary columns, and enabling index usage.
