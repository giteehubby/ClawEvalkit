#!/bin/bash

# Launch script for Conversational Materials Science Assistant
# This script activates the environment and launches the Streamlit app

# Get the workspace root directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
WORKSPACE_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🚀 Launching Conversational Materials Science Assistant..."
echo "📁 Workspace: $WORKSPACE_ROOT"

# Check if virtual environment exists
VENV_PATH="$WORKSPACE_ROOT/.venv"
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment not found at $VENV_PATH"
    echo "Please create it first: python -m venv .venv"
    exit 1
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Check if required environment variables are set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  Warning: OPENAI_API_KEY not set"
    echo "   Please set it in your .env file"
fi

if [ -z "$SUPABASE_URL" ]; then
    echo "⚠️  Warning: SUPABASE_URL not set"
    echo "   Please set it in your .env file"
fi

# Change to the conversational_system directory
cd "$SCRIPT_DIR"

# Launch Streamlit
echo "🌐 Starting Streamlit app..."
echo "   Open your browser at: http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

streamlit run frontend/streamlit_app.py
