#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

cat > "$WORKSPACE/optimized_queries.sql" << 'SQL'
-- Query 1
SELECT id, email, name FROM customers WHERE email = 'test@example.com';

-- Query 2
SELECT o.id, o.order_date, o.total_amount
FROM orders o
JOIN customers c ON o.customer_id = c.id
WHERE c.country = 'US' AND o.order_date >= '2024-01-01';

-- Query 3
SELECT p.name, SUM(oi.quantity) as total_qty
FROM order_items oi
JOIN products p ON oi.product_id = p.id
WHERE oi.quantity > 0
GROUP BY p.id, p.name
HAVING total_qty > 10;
SQL

python3 -c "
import json
recs = [
    {'table': 'customers', 'columns': ['email'], 'reason': 'Enable direct lookup by email without LOWER()'},
    {'table': 'orders', 'columns': ['customer_id', 'order_date'], 'reason': 'Composite index for JOIN + date filter'},
    {'table': 'order_items', 'columns': ['product_id', 'quantity'], 'reason': 'Covering index for aggregation query'},
    {'table': 'products', 'columns': ['name'], 'reason': 'Index for product name lookups in GROUP BY'}
]
with open('$WORKSPACE/index_recommendations.json', 'w') as f:
    json.dump(recs, f, indent=2)
"

echo "Optimized queries and index recommendations saved to $WORKSPACE/"
