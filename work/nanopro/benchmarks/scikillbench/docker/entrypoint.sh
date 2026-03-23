#!/bin/bash
# Entrypoint script for CASCADE Docker container
# Cleans up temp files and starts the application

set -e

# Activate virtual environment
source /app/.venv/bin/activate

echo "🚀 Starting CASCADE Conversational System..."

# Clean up temp_code directory to avoid accumulation
if [ -d "/app/temp_code" ]; then
    echo "🧹 Cleaning up temp_code directory..."
    rm -rf /app/temp_code/*
fi

# Check required environment variables
check_env_var() {
    if [ -z "${!1}" ]; then
        echo "⚠️  Warning: $1 not set"
    else
        echo "✅ $1 is configured"
    fi
}

echo ""
echo "📋 Checking environment variables..."
check_env_var "OPENAI_API_KEY"
check_env_var "SUPABASE_URL"
check_env_var "SUPABASE_SERVICE_KEY"
check_env_var "NEO4J_URI"
check_env_var "NEO4J_USER"
check_env_var "NEO4J_PASSWORD"
check_env_var "TAVILY_API_KEY"
check_env_var "MP_API_KEY"
echo ""

# Set default Neo4j URI if not provided (for docker-compose network)
if [ -z "$NEO4J_URI" ]; then
    export NEO4J_URI="bolt://neo4j:7687"
    echo "📌 Using default NEO4J_URI: $NEO4J_URI"
fi

echo "🌐 Starting application..."
echo "   Access the UI at: http://localhost:8501"
echo ""

# Execute the main command
exec "$@"
