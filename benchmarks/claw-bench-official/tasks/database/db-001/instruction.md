# Task: Basic SQL Query

You are given a SQLite database schema and data in `workspace/database.sql`.

## Goal

Write a SQL query that finds all employees in the **Engineering** department with a salary greater than **80000**.

## Requirements

1. Read `workspace/database.sql` to understand the table schema and data.
2. Write a SELECT query that returns **all columns** for matching employees.
3. Results must be ordered by `salary` descending.
4. Save your query to `workspace/query.sql`.
5. Execute the query against the database and save the results as `workspace/results.json` — a JSON array of objects, one per row, with column names as keys.

## Example Output Format

```json
[
  {"id": 5, "name": "Alice", "department": "Engineering", "salary": 95000, "hire_date": "2021-03-15"}
]
```

## Notes

- Use SQLite-compatible SQL syntax.
- The query should be a single SELECT statement.
- The JSON output must be valid and parseable.
