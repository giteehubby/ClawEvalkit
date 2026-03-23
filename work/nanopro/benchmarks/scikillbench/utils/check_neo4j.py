#!/usr/bin/env python3
"""
Check if Neo4j database is completely cleaned

This script connects to Neo4j and outputs the count of all major node types.
"""

import os
import sys
import asyncio
from pathlib import Path
from neo4j import GraphDatabase

def get_project_root():
    """Get the project root directory by looking for .git directory"""
    current_path = Path(__file__).resolve()
    # Navigate up to find project root (directory containing .git)
    while not (current_path / ".git").exists() and current_path.parent != current_path:
        current_path = current_path.parent
    if (current_path / ".git").exists():
        return current_path
    else:
        raise FileNotFoundError("Could not find project root (no .git directory found)")

def read_neo4j_env_vars():
    """Read Neo4j environment variables from environment or .env file"""
    # First try to get from environment variables
    neo4j_uri = os.environ.get('NEO4J_URI')
    neo4j_user = os.environ.get('NEO4J_USER')
    neo4j_password = os.environ.get('NEO4J_PASSWORD')
    
    # If not found in environment, try .env file
    if not all([neo4j_uri, neo4j_user, neo4j_password]):
        project_root = get_project_root()
        env_path = project_root / "mcp_servers_and_tools/research_server" / ".env"
        
        if env_path.exists():
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("NEO4J_URI=") and not neo4j_uri:
                        neo4j_uri = line.split("=", 1)[1].strip()
                    elif line.startswith("NEO4J_USER=") and not neo4j_user:
                        neo4j_user = line.split("=", 1)[1].strip()
                    elif line.startswith("NEO4J_PASSWORD=") and not neo4j_password:
                        neo4j_password = line.split("=", 1)[1].strip()
    
    return neo4j_uri, neo4j_user, neo4j_password

async def check_neo4j_clean():
    """Check Neo4j database cleaning status"""
    
    # Get Neo4j connection details from environment or .env file
    neo4j_uri, neo4j_user, neo4j_password = read_neo4j_env_vars()
    
    if not all([neo4j_uri, neo4j_user, neo4j_password]):
        print("❌ Neo4j environment variables not found. Please set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD in your environment or .env file.")
        return
    
    try:
        # Connect to Neo4j
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        
        print(f"🔌 Connecting to Neo4j: {neo4j_uri}")
        
        with driver.session() as session:
            print("✅ Successfully connected to Neo4j")
            
            # First, get all available labels in the database
            result = session.run("CALL db.labels() YIELD label RETURN label")
            available_labels = [record["label"] for record in result]
            
            print(f"\n📊 Database contains {len(available_labels)} node types:")
            for label in sorted(available_labels):
                print(f"   • {label}")
            
            # Check different node types (only if they exist)
            node_types = ["Repository", "File", "Class", "Method", "Function", "Attribute"]
            
            print(f"\n📈 Node counts by type:")
            print("─" * 40)
            
            total_nodes = 0
            for node_type in node_types:
                if node_type in available_labels:
                    result = session.run(f"MATCH (n:{node_type}) RETURN count(n) as count")
                    count = result.single()["count"]
                    total_nodes += count
                    print(f"  {node_type:12} : {count:>6}")
                else:
                    print(f"  {node_type:12} : {0:>6} (not found)")
            
            print("─" * 40)
            print(f"  {'Total':12} : {total_nodes:>6}")
            
            # Show repository details if any exist
            if "Repository" in available_labels:
                print(f"\n📚 Repository Details:")
                print("─" * 40)
                result = session.run("""
                    MATCH (r:Repository) 
                    RETURN r.name as name
                    ORDER BY r.name
                """)
                repos = list(result)
                
                if repos:
                    for i, repo in enumerate(repos, 1):
                        name = repo["name"] or "Unknown"
                        print(f"  {i}. {name}")
                    print()
                else:
                    print("  No repositories found")
            
            # Additional check for any other nodes
            result = session.run("MATCH (n) RETURN count(n) as count")
            actual_total = result.single()["count"]
            
            if actual_total != total_nodes:
                print(f"\n⚠️  Note: Total nodes in database ({actual_total}) differs from sum above ({total_nodes})")
                print("   This may indicate nodes with other labels or unlabeled nodes.")
                print("   💡 Tip: These might be memory-related nodes from conversational system.")
                print("      • Check: python utils/clean_neo4j_memory.py --mode stats")
                print("      • Preview deletion: python utils/clean_neo4j_memory.py --mode memory")
                print("      • Actually clean: python utils/clean_neo4j_memory.py --mode memory --execute")
            
        print("\n✅ Check completed")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'driver' in locals():
            driver.close()

def main():
    """Main function"""
    print("🗄️  Neo4j Database Status Check")
    print("=" * 50)
    asyncio.run(check_neo4j_clean())

if __name__ == "__main__":
    main() 