#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

cat > "$WORKSPACE/migrate.sql" << 'SQL'
-- Create new normalized tables
CREATE TABLE IF NOT EXISTS users_new (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    street TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    zip TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users_new(id)
);

-- Migrate user core data
INSERT INTO users_new (id, name, email, created_at)
SELECT id, name, email, created_at FROM users;

-- Migrate addresses by parsing the comma-separated address string
-- Format: "street, city, state, zip"
INSERT INTO addresses (user_id, street, city, state, zip)
SELECT
    id AS user_id,
    TRIM(SUBSTR(address, 1, INSTR(address, ',') - 1)) AS street,
    TRIM(SUBSTR(
        address,
        INSTR(address, ',') + 1,
        INSTR(SUBSTR(address, INSTR(address, ',') + 1), ',') - 1
    )) AS city,
    TRIM(SUBSTR(
        SUBSTR(address, INSTR(address, ',') + 1),
        INSTR(SUBSTR(address, INSTR(address, ',') + 1), ',') + 1,
        INSTR(
            SUBSTR(
                SUBSTR(address, INSTR(address, ',') + 1),
                INSTR(SUBSTR(address, INSTR(address, ',') + 1), ',') + 1
            ),
            ','
        ) - 1
    )) AS state,
    TRIM(SUBSTR(
        address,
        LENGTH(address) - INSTR(REPLACE(REPLACE(address, ' ', ''), ',', ',,'), ',,') + 2
    )) AS zip
FROM users;

-- Alternative simpler approach using a CTE for clarity:
DELETE FROM addresses;

INSERT INTO addresses (user_id, street, city, state, zip)
WITH split AS (
    SELECT
        id,
        address,
        TRIM(SUBSTR(address, 1, INSTR(address, ',') - 1)) AS street,
        SUBSTR(address, INSTR(address, ',') + 1) AS rest1
    FROM users
),
split2 AS (
    SELECT
        id,
        street,
        TRIM(SUBSTR(rest1, 1, INSTR(rest1, ',') - 1)) AS city,
        SUBSTR(rest1, INSTR(rest1, ',') + 1) AS rest2
    FROM split
),
split3 AS (
    SELECT
        id,
        street,
        city,
        TRIM(SUBSTR(rest2, 1, INSTR(rest2, ',') - 1)) AS state,
        TRIM(SUBSTR(rest2, INSTR(rest2, ',') + 1)) AS zip
    FROM split2
)
SELECT id, street, city, state, zip FROM split3;
SQL

echo "Migration script saved to $WORKSPACE/migrate.sql"
