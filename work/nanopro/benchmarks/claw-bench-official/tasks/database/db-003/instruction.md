# Task: Schema Design from Requirements

You are given a requirements document at `workspace/requirements.txt` that describes a blog system.

## Goal

Design and output a complete SQL schema (CREATE TABLE statements) for the described blog system.

## Requirements

1. Read `workspace/requirements.txt` carefully.
2. Create a schema with **5 tables**: `users`, `posts`, `comments`, `tags`, and `post_tags` (junction table for many-to-many).
3. Each table must have appropriate columns with proper data types.
4. Use proper PRIMARY KEY, FOREIGN KEY, and NOT NULL constraints.
5. The `post_tags` table must implement the many-to-many relationship between posts and tags.
6. Save the complete schema as `workspace/schema.sql`.

## Table Requirements

- **users**: id (PK), username, email, created_at
- **posts**: id (PK), user_id (FK→users), title, content, published_at
- **comments**: id (PK), post_id (FK→posts), user_id (FK→users), body, created_at
- **tags**: id (PK), name
- **post_tags**: post_id (FK→posts), tag_id (FK→tags), composite PK

## Notes

- Use SQLite-compatible SQL syntax.
- All foreign keys must reference valid parent tables.
- The schema must execute without errors on a fresh SQLite database.
