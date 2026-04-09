#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

cat > "$WORKSPACE/query.sql" << 'SQL'
SELECT
    c.name AS customer_name,
    c.city AS city,
    SUM(o.amount) AS total_spend
FROM customers c
JOIN orders o ON c.id = o.customer_id
GROUP BY c.id, c.name, c.city
ORDER BY total_spend DESC;
SQL

python3 -c "
import sqlite3, json

db = sqlite3.connect(':memory:')
db.row_factory = sqlite3.Row

with open('$WORKSPACE/schema.sql') as f:
    db.executescript(f.read())

with open('$WORKSPACE/query.sql') as f:
    query = f.read()

rows = db.execute(query).fetchall()
results = [dict(r) for r in rows]

with open('$WORKSPACE/results.json', 'w') as f:
    json.dump(results, f, indent=2)

db.close()
"

echo "Query and results saved to $WORKSPACE/"
