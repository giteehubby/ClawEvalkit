"""
Check Supabase connection and table status
"""

import os
import psycopg2
from psycopg2 import sql

print("="*80)
print("SUPABASE CONNECTION CHECK")
print("="*80)

connection_string = os.getenv('SUPABASE_DATABASE_URL')

if not connection_string:
    print("❌ SUPABASE_DATABASE_URL not set")
    exit(1)

try:
    print("\n1️⃣  Connecting to Supabase...")
    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()
    print("✅ Connected successfully")

    # Check if conversational_memories table exists (check both public and vecs schemas)
    print("\n2️⃣  Checking for 'conversational_memories' table...")

    # Check in vecs schema (mem0 with Supabase uses vecs extension)
    cursor.execute("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_name = 'conversational_memories'
    """)
    results = cursor.fetchall()

    if results:
        for schema, table_name in results:
            print(f"✅ Table '{table_name}' exists in schema '{schema}'")

            # Count records
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.{table_name}")
            count = cursor.fetchone()[0]
            print(f"   Records in table: {count}")

            # Show sample
            if count > 0:
                cursor.execute(f"SELECT * FROM {schema}.{table_name} LIMIT 3")
                columns = [desc[0] for desc in cursor.description]
                print(f"   Columns: {columns}")
                print("\n   Sample records:")
                for row in cursor.fetchall():
                    print(f"   - {row[:3]}...")  # Show first 3 fields
    else:
        print("❌ Table 'conversational_memories' does NOT exist in any schema")
        print("\n   Mem0 should create this table automatically.")
        print("   If it doesn't exist, mem0 might be failing silently.")

    # Check for mem0-related tables
    print("\n3️⃣  Checking for other mem0 tables...")
    cursor.execute("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_name LIKE '%mem%'
        AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name
    """)
    mem_tables = cursor.fetchall()

    if mem_tables:
        print("   Found mem0-related tables:")
        for schema, table_name in mem_tables:
            cursor.execute(f"SELECT COUNT(*) FROM {schema}.{table_name}")
            count = cursor.fetchone()[0]
            print(f"   - {schema}.{table_name}: {count} records")
    else:
        print("   ⚠️  No mem0-related tables found")

    # List all tables by schema
    print("\n4️⃣  All tables by schema:")
    cursor.execute("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema IN ('public', 'vecs')
        ORDER BY table_schema, table_name
    """)
    all_tables = cursor.fetchall()

    current_schema = None
    for schema, table_name in all_tables[:30]:  # Show first 30
        if schema != current_schema:
            print(f"\n   Schema: {schema}")
            current_schema = schema
        print(f"   - {table_name}")

    if len(all_tables) > 30:
        print(f"\n   ... and {len(all_tables) - 30} more tables")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
