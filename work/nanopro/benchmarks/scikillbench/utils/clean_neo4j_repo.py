#!/usr/bin/env python3
"""
Clear code structure nodes and relationships in Neo4j (research-server data)
This script only deletes nodes WITHOUT user_id property (code structure).
Memory data from conversational system (nodes with user_id) will be preserved.
"""
import asyncio
import sys
import os
from pathlib import Path

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

async def clean_neo4j_all():
    neo4j_uri, neo4j_user, neo4j_password = read_neo4j_env_vars()
    
    if not all([neo4j_uri, neo4j_user, neo4j_password]):
        raise Exception("Neo4j environment variables not found. Please set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD in your environment or .env file.")
    
    print(f"Connecting to Neo4j: {neo4j_uri}")
    project_root = get_project_root()
    sys.path.append(str(project_root / "mcp_servers_and_tools/research_server" / "knowledge_graphs"))
    from parse_repo_into_neo4j import DirectNeo4jExtractor
    extractor = DirectNeo4jExtractor(neo4j_uri, neo4j_user, neo4j_password)
    await extractor.initialize()
    print("✓ Successfully connected to Neo4j")
    async with extractor.driver.session() as session:
        print("Starting to clear code structure nodes (without user_id property)...")
        await session.run("MATCH (n) WHERE n.user_id IS NULL DETACH DELETE n")
        print("✓ Code structure nodes and relationships have been cleared")
        print("✓ Memory data (nodes with user_id) has been preserved")
        print("\n💡 To clean memory data from conversational system:")
        print("   • Check: python utils/clean_neo4j_memory.py --mode stats")
        print("   • Preview deletion: python utils/clean_neo4j_memory.py --mode memory")
        print("   • Actually clean: python utils/clean_neo4j_memory.py --mode memory --execute")
    await extractor.close()
    print("\n✓ Database connection closed")

def main():
    print("Clear Neo4j code structure data (research-server)")
    print("="*50)
    asyncio.run(clean_neo4j_all())

if __name__ == "__main__":
    main() 