# Task: Multi-Table JOIN with Aggregation

You are given a SQLite database schema with three related tables in `workspace/schema.sql`.

## Goal

Write a SQL query that computes the **total spend per customer**, including the customer's name and city, sorted by total spend in descending order.

## Requirements

1. Read `workspace/schema.sql` to understand the tables: `orders`, `customers`, and `products`.
2. Write a query that JOINs the relevant tables and uses GROUP BY with SUM to aggregate.
3. The result columns must be: `customer_name`, `city`, `total_spend`.
4. Results must be sorted by `total_spend` descending.
5. Include ALL customers that have orders (no customers with zero orders needed).
6. Save your query to `workspace/query.sql`.
7. Execute the query and save the results as `workspace/results.json` — a JSON array of objects.

## Example Output Format

```json
[
  {"customer_name": "Alice", "city": "New York", "total_spend": 1500}
]
```

## Notes

- The `total_spend` is the sum of `orders.amount` for each customer.
- Use SQLite-compatible SQL syntax.
- The products table is provided for schema completeness but is not needed for the spend calculation.
