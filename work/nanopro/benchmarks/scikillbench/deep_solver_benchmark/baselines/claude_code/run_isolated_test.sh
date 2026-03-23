#!/bin/bash

# Run Claude Code agent with COMPLETE ISOLATION
# - Agent works only in /tmp (tmpfs)
# - Agent cannot see any files or previous results
# - Each run is completely independent
# - Container is destroyed after run
# - Results are saved to test_results/
# - Log is saved to test_log/

QUESTION_FILE="${1:-../../../benchmark_tasks_and_results/questions_and_answers/data/data_retrieval/materials_project.json}"
QUESTION_INDEX="${2:-0}"
QUERY_LEVEL="${3:-1}"
MODEL="${4:-claude-sonnet-4-5}"
REPETITION="${5:-1}"
CREATE_AGENT_LOG="${6:-true}"  # create separate agent log file (default: true)
RESULTS_FILE="${7:-}"  # Optional: results file path (if empty, use default)
ENABLE_TRACING="${8:-false}"  # Enable detailed tracing (default: false)
TRACE_DIR="${9:-test_tracing}"  # Tracing directory (default: test_tracing)

TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Extract benchmark name for display
BENCHMARK_NAME=$(basename "$QUESTION_FILE" .json)

# Determine results file path
if [ -z "$RESULTS_FILE" ]; then
    # Default: use descriptive name with question details and timestamp
    RESULTS_FILE="test_results/results_${BENCHMARK_NAME}_q${QUESTION_INDEX}_level${QUERY_LEVEL}_rep${REPETITION}_${TIMESTAMP}.json"
fi

# Agent-specific log directory (for detailed agent output only)
AGENT_LOG_DIR="agent_logs"
AGENT_LOG_FILE="${AGENT_LOG_DIR}/agent_${BENCHMARK_NAME}_q${QUESTION_INDEX}_level${QUERY_LEVEL}_rep${REPETITION}_${TIMESTAMP}.log"

# Tracing file (if tracing is enabled)
TRACE_FILE="${TRACE_DIR}/trace_${BENCHMARK_NAME}_q${QUESTION_INDEX}_level${QUERY_LEVEL}_rep${REPETITION}_${TIMESTAMP}.log"

echo "=========================================="
echo "Claude Code Isolated Test"
echo "=========================================="
echo "Question file: $QUESTION_FILE"
echo "Benchmark: $BENCHMARK_NAME"
echo "Question index: $QUESTION_INDEX"
echo "Query level: $QUERY_LEVEL"
echo "Model: $MODEL"
echo "Repetition: $REPETITION"
echo "Results file: $RESULTS_FILE"
if [ "$CREATE_AGENT_LOG" = "true" ]; then
    echo "Agent log file: $AGENT_LOG_FILE"
fi
if [ "$ENABLE_TRACING" = "true" ]; then
    echo "Tracing enabled: $TRACE_FILE"
fi
echo "=========================================="
echo ""

# Create directories
mkdir -p test_results
mkdir -p "$AGENT_LOG_DIR"
if [ "$ENABLE_TRACING" = "true" ]; then
    mkdir -p "$TRACE_DIR"
fi

# Extract question from benchmark (remove answer fields)
echo "Extracting question from benchmark..."

# Create temporary Python script
TMP_SCRIPT=$(mktemp)
cat > "$TMP_SCRIPT" << 'PYTHON_SCRIPT'
import json
import sys

question_file = sys.argv[1]
question_index = int(sys.argv[2])

with open(question_file) as f:
    questions = json.load(f)

question_data = questions[question_index]

# Extract only safe fields (NO ANSWER)
safe_data = {
    'user_query': question_data.get('user_query', {}),
    'output_type': question_data.get('output_type', ''),
    'unit': question_data.get('unit', '')
}

# Also save answer for later comparison (not passed to agent)
print("ANSWER_FOR_COMPARISON:", json.dumps(question_data.get('answer', 'N/A')))
print("TOLERANCE_FOR_COMPARISON:", json.dumps(question_data.get('absolute_tolerance', 'N/A')))

# Output question data
print(json.dumps(safe_data))
PYTHON_SCRIPT

QUESTION_JSON=$(python3 "$TMP_SCRIPT" "$QUESTION_FILE" "$QUESTION_INDEX")
rm "$TMP_SCRIPT"

# Extract answer and tolerance for later
ANSWER=$(echo "$QUESTION_JSON" | grep "ANSWER_FOR_COMPARISON:" | sed 's/ANSWER_FOR_COMPARISON: //')
TOLERANCE=$(echo "$QUESTION_JSON" | grep "TOLERANCE_FOR_COMPARISON:" | sed 's/TOLERANCE_FOR_COMPARISON: //')
QUESTION_JSON=$(echo "$QUESTION_JSON" | grep -v "ANSWER_FOR_COMPARISON:" | grep -v "TOLERANCE_FOR_COMPARISON:")

echo "Question extracted (answer hidden from agent)"
echo ""

# Build Docker image name
IMAGE_NAME="claude_code-claude-code-baseline"

echo "Running agent in completely isolated container..."
echo "(Agent only works in tmpfs)"
echo ""

# Extract question components from JSON
QUERY=$(echo "$QUESTION_JSON" | python3 -c "import json, sys; data = json.load(sys.stdin); print(data['user_query'].get('$QUERY_LEVEL', ''))")
OUTPUT_TYPE=$(echo "$QUESTION_JSON" | python3 -c "import json, sys; data = json.load(sys.stdin); print(data.get('output_type', ''))")
UNIT=$(echo "$QUESTION_JSON" | python3 -c "import json, sys; data = json.load(sys.stdin); print(data.get('unit', ''))")

# Base64 encode to safely pass through Docker (avoids all shell escaping issues)
QUERY_B64=$(echo -n "$QUERY" | base64 -w 0)
OUTPUT_TYPE_B64=$(echo -n "$OUTPUT_TYPE" | base64 -w 0)
UNIT_B64=$(echo -n "$UNIT" | base64 -w 0)

# Build Docker run command arguments
DOCKER_ARGS="--query"
if [ "$ENABLE_TRACING" = "true" ]; then
    DOCKER_CMD_ARGS="[\"--query\", base64.b64decode(os.environ[\"QUESTION_QUERY_B64\"]).decode(), \"--output-type\", base64.b64decode(os.environ[\"QUESTION_OUTPUT_TYPE_B64\"]).decode(), \"--unit\", base64.b64decode(os.environ[\"QUESTION_UNIT_B64\"]).decode(), \"--query-level\", \"$QUERY_LEVEL\", \"--model\", \"$MODEL\", \"--enable-tracing\"]"
else
    DOCKER_CMD_ARGS="[\"--query\", base64.b64decode(os.environ[\"QUESTION_QUERY_B64\"]).decode(), \"--output-type\", base64.b64decode(os.environ[\"QUESTION_OUTPUT_TYPE_B64\"]).decode(), \"--unit\", base64.b64decode(os.environ[\"QUESTION_UNIT_B64\"]).decode(), \"--query-level\", \"$QUERY_LEVEL\", \"--model\", \"$MODEL\"]"
fi

# Run in Docker with complete isolation - NO FILE MOUNTS!
# Pass encoded data via environment variables
# Using --network=host to allow access to host's MongoDB (for pymatgen-db benchmarks)
OUTPUT=$(sg docker -c "docker run --rm \
    --network=host \
    --tmpfs /tmp:size=2G,exec \
    -e MP_API_KEY=$MP_API_KEY \
    -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
    -e QUESTION_QUERY_B64=$QUERY_B64 \
    -e QUESTION_OUTPUT_TYPE_B64=$OUTPUT_TYPE_B64 \
    -e QUESTION_UNIT_B64=$UNIT_B64 \
    --security-opt=no-new-privileges:true \
    --cap-drop=ALL \
    --memory=8g \
    --cpus=4 \
    $IMAGE_NAME \
    python -c 'import base64, sys, os; args = $DOCKER_CMD_ARGS; sys.argv = [\"claude_code_runner.py\"] + args; exec(open(\"/usr/local/bin/claude_code_runner.py\").read())' \
    2>&1")

echo ""
echo "=========================================="
echo "Container execution completed"
echo "=========================================="
echo ""

# Extract log from output
# The output may contain error messages before the LOG markers
LOG_TEXT=$(echo "$OUTPUT" | sed -n '/CLAUDE_CODE_LOG_START/,/CLAUDE_CODE_LOG_END/p' | grep -v "CLAUDE_CODE_LOG")

# Save or output agent's detailed log based on CREATE_AGENT_LOG parameter
if [ "$CREATE_AGENT_LOG" = "true" ]; then
    # Single-run mode: create separate agent log file
    if [ -z "$LOG_TEXT" ]; then
        echo "Warning: LOG markers not found, saving full output to agent log file"
        echo "$OUTPUT" > "$AGENT_LOG_FILE"
    else
        echo "$LOG_TEXT" > "$AGENT_LOG_FILE"
    fi
    echo "Agent log saved to: $AGENT_LOG_FILE"
else
    # Benchmark mode: output to stdout (captured by parent process)
    echo ""
    echo "=========================================="
    echo "AGENT DETAILED OUTPUT"
    echo "=========================================="
    if [ -z "$LOG_TEXT" ]; then
        echo "$OUTPUT"
    else
        echo "$LOG_TEXT"
    fi
    echo "=========================================="
fi
echo ""

# Extract result JSON from output
RESULT_JSON=$(echo "$OUTPUT" | sed -n '/CLAUDE_CODE_RESULT_START/,/CLAUDE_CODE_RESULT_END/p' | grep -v "CLAUDE_CODE_RESULT")

if [ -z "$RESULT_JSON" ]; then
    echo "❌ Failed to extract result from output"
    exit 1
fi

echo "=========================================="
echo "Extracted Result:"
echo "=========================================="
echo "$RESULT_JSON"
echo ""

# Extract and save trace data if tracing is enabled
if [ "$ENABLE_TRACING" = "true" ]; then
    TRACE_JSON=$(echo "$OUTPUT" | sed -n '/CLAUDE_CODE_TRACE_START/,/CLAUDE_CODE_TRACE_END/p' | grep -v "CLAUDE_CODE_TRACE")

    if [ -n "$TRACE_JSON" ]; then
        echo "$TRACE_JSON" > "$TRACE_FILE"
        echo "Trace data saved to: $TRACE_FILE"
    else
        echo "Warning: Tracing was enabled but no trace data found"
        # Save the full Docker output for debugging
        echo "Saving full Docker output for debugging..."
        echo "================================================================================">  "$TRACE_FILE"
        echo "DOCKER OUTPUT DEBUG (No trace data was generated)" >> "$TRACE_FILE"
        echo "================================================================================" >> "$TRACE_FILE"
        echo "Question: $(echo "$RESULT_JSON" | python3 -c "import json, sys; print(json.load(sys.stdin)['question'])")" >> "$TRACE_FILE"
        echo "Processed Output: $(echo "$RESULT_JSON" | python3 -c "import json, sys; print(json.load(sys.stdin)['processed_output'])")" >> "$TRACE_FILE"
        echo "Execution Time: $(echo "$RESULT_JSON" | python3 -c "import json, sys; print(json.load(sys.stdin)['execution_time_seconds'])")" >> "$TRACE_FILE"
        echo "================================================================================" >> "$TRACE_FILE"
        echo "" >> "$TRACE_FILE"
        echo "FULL DOCKER CONTAINER OUTPUT:" >> "$TRACE_FILE"
        echo "================================================================================" >> "$TRACE_FILE"
        echo "$OUTPUT" >> "$TRACE_FILE"
        echo "================================================================================" >> "$TRACE_FILE"
    fi
    echo ""
fi

# Build final result
# Format: {level_id, question, repetition, timestamp, execution_time_seconds, answer, tolerance, processed_output, benchmark}
# Note: answer and tolerance need to be stored as strings for compatibility with benchmark_evaluator
FINAL_RESULT=$(echo "$RESULT_JSON" | python3 -c "
import json, sys
result = json.load(sys.stdin)

# Parse answer and tolerance
answer = $ANSWER
tolerance = $TOLERANCE

# Extract tolerance for the specific query level
# If tolerance is a dict with level keys, extract the value for current level
if isinstance(tolerance, dict) and '$QUERY_LEVEL' in tolerance:
    tolerance = tolerance['$QUERY_LEVEL']

# Store answer and tolerance as JSON strings for evaluator compatibility
result['answer'] = json.dumps(answer)
result['tolerance'] = json.dumps(tolerance)
result['repetition'] = $REPETITION
result['benchmark'] = '$QUESTION_FILE'
print(json.dumps(result, indent=2))
")

# Append to results file
if [ -f "$RESULTS_FILE" ]; then
    # File exists, append to array
    python3 << EOF
import json

with open('$RESULTS_FILE') as f:
    results = json.load(f)

results.append($FINAL_RESULT)

with open('$RESULTS_FILE', 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
EOF
else
    # Create new file
    echo "[$FINAL_RESULT]" > "$RESULTS_FILE"
fi

echo "=========================================="
echo "Test completed!"
echo "=========================================="
echo "Results saved to: $RESULTS_FILE"
if [ "$CREATE_AGENT_LOG" = "true" ]; then
    echo "Agent log saved to: $AGENT_LOG_FILE"
fi
echo ""

# Print final output
PROCESSED_OUTPUT=$(echo "$FINAL_RESULT" | python3 -c "import json, sys; print(json.load(sys.stdin)['processed_output'])")
echo "===FINAL_PROCESSED_OUTPUT_START==="
echo "$PROCESSED_OUTPUT"
echo "===FINAL_PROCESSED_OUTPUT_END==="
