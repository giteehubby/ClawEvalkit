# Task: Data Migration Script

You are given two schema files in your workspace:

- `workspace/old_schema.sql` — the current (flat) database schema with sample data
- `workspace/new_schema.sql` — the target (normalized) schema

## Goal

Write a SQL migration script that transforms data from the old schema to the new schema.

## Context

The old schema has a single `users` table with address stored as a single string field (e.g., `"123 Main St, Springfield, IL, 62701"`). The new schema normalizes this into two tables: `users` (without address) and `addresses` (with parsed street, city, state, zip fields).

## Requirements

1. Read both schema files to understand the source and target structures.
2. Write `workspace/migrate.sql` that:
   - Creates the new `users_new` and `addresses` tables (matching new_schema.sql structure).
   - Migrates user data from the old `users` table to `users_new` (id, name, email, created_at).
   - Parses the `address` string and inserts into the `addresses` table with separate fields: `user_id`, `street`, `city`, `state`, `zip`.
   - The address string format is: `"street, city, state, zip"` (comma-separated, 4 parts).
3. The migration must handle all 8 users in the old data.
4. After migration, every user must have exactly one address row.

## Notes

- Use SQLite-compatible SQL syntax. SQLite string functions like `SUBSTR`, `INSTR`, `TRIM`, `REPLACE` are available.
- You may use a combination of SQL and string manipulation.
- The migration script should be idempotent-safe (use IF NOT EXISTS for CREATE TABLE).
