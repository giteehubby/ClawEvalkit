"""
Clean Neo4j Memory Data

Safely cleans memory data from conversational system without affecting
research-server code structure data.

Usage:
    python clean_neo4j_memory.py --mode [memory|all|user]

Modes:
    memory: Clean only memory nodes (nodes with user_id property) - SAFE
    all:    Clean ALL data including research-server code structure - DANGEROUS
    user:   Clean only specific user's memory data
"""

import os
import argparse
from neo4j import GraphDatabase


def get_neo4j_connection():
    """Get Neo4j connection details"""
    url = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USER', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')
    return url, username, password


def clean_memory_only(driver, dry_run=True):
    """
    Clean only memory nodes (nodes with user_id property).
    Safe - won't affect research-server code structure.
    """
    print("\n" + "="*80)
    print("CLEANING MEMORY DATA ONLY")
    print("="*80)

    with driver.session() as session:
        # Count memory nodes
        result = session.run("""
            MATCH (n)
            WHERE n.user_id IS NOT NULL
            RETURN count(n) as count
        """)
        memory_count = result.single()['count']

        # Count memory relationships
        result = session.run("""
            MATCH (a)-[r]-(b)
            WHERE a.user_id IS NOT NULL OR b.user_id IS NOT NULL
            RETURN count(r) as count
        """)
        rel_count = result.single()['count']

        print(f"\n📊 Memory data to delete:")
        print(f"   - Nodes: {memory_count}")
        print(f"   - Relationships: {rel_count}")

        if dry_run:
            print("\n⚠️  DRY RUN - No data will be deleted")
            print("   Run with --execute to actually delete")

            # Show sample
            result = session.run("""
                MATCH (n)
                WHERE n.user_id IS NOT NULL
                RETURN labels(n) as labels, n.user_id as user_id, n.name as name
                LIMIT 10
            """)
            print("\n   Sample nodes to be deleted:")
            for record in result:
                print(f"   - [{record['labels'][0]}] {record['name']} (user: {record['user_id']})")

            return

        # Actually delete
        print("\n🗑️  Deleting memory data...")

        # Delete relationships first
        session.run("""
            MATCH (a)-[r]-(b)
            WHERE a.user_id IS NOT NULL OR b.user_id IS NOT NULL
            DELETE r
        """)
        print(f"   ✅ Deleted {rel_count} relationships")

        # Delete nodes
        session.run("""
            MATCH (n)
            WHERE n.user_id IS NOT NULL
            DELETE n
        """)
        print(f"   ✅ Deleted {memory_count} nodes")

        print("\n✅ Memory data cleaned successfully!")
        print("   Research-server code structure data is intact.")


def clean_specific_user(driver, user_id, dry_run=True):
    """Clean only specific user's memory data"""
    print("\n" + "="*80)
    print(f"CLEANING USER: {user_id}")
    print("="*80)

    with driver.session() as session:
        # Count user nodes
        result = session.run("""
            MATCH (n)
            WHERE n.user_id = $user_id
            RETURN count(n) as count
        """, user_id=user_id)
        node_count = result.single()['count']

        # Count relationships
        result = session.run("""
            MATCH (a)-[r]-(b)
            WHERE a.user_id = $user_id OR b.user_id = $user_id
            RETURN count(r) as count
        """, user_id=user_id)
        rel_count = result.single()['count']

        print(f"\n📊 Data to delete for user '{user_id}':")
        print(f"   - Nodes: {node_count}")
        print(f"   - Relationships: {rel_count}")

        if node_count == 0:
            print(f"\n⚠️  No data found for user: {user_id}")
            return

        if dry_run:
            print("\n⚠️  DRY RUN - No data will be deleted")
            print("   Run with --execute to actually delete")

            # Show sample
            result = session.run("""
                MATCH (n)
                WHERE n.user_id = $user_id
                RETURN labels(n) as labels, n.name as name, n.mentions as mentions
                ORDER BY n.mentions DESC
                LIMIT 10
            """, user_id=user_id)
            print("\n   Sample nodes to be deleted:")
            for record in result:
                mentions = record.get('mentions', 'N/A')
                print(f"   - [{record['labels'][0]}] {record['name']} (mentioned {mentions}x)")

            return

        # Actually delete
        print(f"\n🗑️  Deleting data for user '{user_id}'...")

        # Delete relationships
        session.run("""
            MATCH (a)-[r]-(b)
            WHERE a.user_id = $user_id OR b.user_id = $user_id
            DELETE r
        """, user_id=user_id)
        print(f"   ✅ Deleted {rel_count} relationships")

        # Delete nodes
        session.run("""
            MATCH (n)
            WHERE n.user_id = $user_id
            DELETE n
        """, user_id=user_id)
        print(f"   ✅ Deleted {node_count} nodes")

        print(f"\n✅ User '{user_id}' data cleaned successfully!")


def clean_all(driver, dry_run=True):
    """
    Clean ALL Neo4j data - DANGEROUS!
    This will delete research-server code structure too!
    """
    print("\n" + "="*80)
    print("⚠️  DANGER: CLEANING ALL DATA")
    print("="*80)

    with driver.session() as session:
        # Count everything
        result = session.run("MATCH (n) RETURN count(n) as count")
        node_count = result.single()['count']

        result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
        rel_count = result.single()['count']

        print(f"\n📊 ALL data to delete:")
        print(f"   - Nodes: {node_count}")
        print(f"   - Relationships: {rel_count}")
        print("\n⚠️  WARNING: This includes research-server code structure data!")

        if dry_run:
            print("\n⚠️  DRY RUN - No data will be deleted")
            print("   Run with --execute to actually delete")

            # Show node types
            result = session.run("""
                MATCH (n)
                RETURN DISTINCT labels(n) as labels, count(*) as count
                ORDER BY count DESC
            """)
            print("\n   Node types:")
            for record in result:
                print(f"   - {record['labels'][0]}: {record['count']} nodes")

            return

        # Require confirmation
        print("\n⚠️  Are you ABSOLUTELY SURE you want to delete ALL data?")
        print("   This will delete research-server code structure!")
        confirm = input("   Type 'DELETE ALL' to confirm: ")

        if confirm != "DELETE ALL":
            print("\n❌ Cancelled")
            return

        # Delete everything
        print("\n🗑️  Deleting ALL data...")

        session.run("MATCH (n) DETACH DELETE n")
        print(f"   ✅ Deleted {node_count} nodes and {rel_count} relationships")

        print("\n✅ All data deleted!")


def show_stats(driver):
    """Show current Neo4j statistics"""
    print("\n" + "="*80)
    print("NEO4J DATABASE STATISTICS")
    print("="*80)

    with driver.session() as session:
        # Total nodes
        result = session.run("MATCH (n) RETURN count(n) as count")
        total_nodes = result.single()['count']

        # Memory nodes
        result = session.run("""
            MATCH (n)
            WHERE n.user_id IS NOT NULL
            RETURN count(n) as count
        """)
        memory_nodes = result.single()['count']

        # Code structure nodes
        code_nodes = total_nodes - memory_nodes

        # Node types
        result = session.run("""
            MATCH (n)
            RETURN DISTINCT labels(n)[0] as label, count(*) as count
            ORDER BY count DESC
            LIMIT 10
        """)

        print(f"\n📊 Total nodes: {total_nodes}")
        print(f"   - Memory data (with user_id): {memory_nodes}")
        print(f"   - Code structure data: {code_nodes}")

        print(f"\n📋 Top node types:")
        for record in result:
            label = record['label']
            count = record['count']
            print(f"   - {label}: {count} nodes")

        # Users
        result = session.run("""
            MATCH (n)
            WHERE n.user_id IS NOT NULL
            RETURN DISTINCT n.user_id as user_id, count(*) as count
            ORDER BY count DESC
        """)

        users = list(result)
        if users:
            print(f"\n👥 Memory users:")
            for record in users:
                print(f"   - {record['user_id']}: {record['count']} nodes")


def main():
    parser = argparse.ArgumentParser(description="Clean Neo4j memory data")
    parser.add_argument(
        '--mode',
        choices=['memory', 'all', 'user', 'stats'],
        default='stats',
        help='Cleaning mode: memory (safe), all (dangerous), user (specific), stats (show only)'
    )
    parser.add_argument(
        '--user-id',
        type=str,
        help='User ID to clean (required for --mode user)'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually execute deletion (default is dry-run)'
    )

    args = parser.parse_args()

    # Get connection
    url, username, password = get_neo4j_connection()

    print("="*80)
    print("NEO4J MEMORY CLEANER")
    print("="*80)
    print(f"Connecting to: {url}")
    print(f"Username: {username}")

    try:
        driver = GraphDatabase.driver(url, auth=(username, password))
        driver.verify_connectivity()
        print("✅ Connected successfully")

        # Show stats first
        if args.mode == 'stats':
            show_stats(driver)
        elif args.mode == 'memory':
            show_stats(driver)
            clean_memory_only(driver, dry_run=not args.execute)
        elif args.mode == 'user':
            if not args.user_id:
                print("\n❌ Error: --user-id required for --mode user")
                return
            show_stats(driver)
            clean_specific_user(driver, args.user_id, dry_run=not args.execute)
        elif args.mode == 'all':
            show_stats(driver)
            clean_all(driver, dry_run=not args.execute)

        driver.close()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Check Neo4j is running")
        print("  2. Check environment variables: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD")
        print("  3. Check credentials are correct")


if __name__ == "__main__":
    main()
