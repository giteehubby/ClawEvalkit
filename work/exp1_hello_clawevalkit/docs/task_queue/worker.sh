#!/usr/bin/env bash
# Task Queue Worker
# Watches task_queue/new/ for task*.md files, executes them one by one,
# moves them to doing/ while running, then done/ when complete.

QUEUE_DIR="$(cd "$(dirname "$0")" && pwd)"
NEW_DIR="$QUEUE_DIR/new"
DOING_DIR="$QUEUE_DIR/doing"
DONE_DIR="$QUEUE_DIR/done"
LOG_FILE="$QUEUE_DIR/worker.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Task Queue Worker started ==="
log "Watching: $NEW_DIR"

while true; do
    # Pick the earliest task by sorted name
    TASK=$(ls "$NEW_DIR"/task*.md 2>/dev/null | sort | head -n1)

    if [ -z "$TASK" ]; then
        sleep 5
        continue
    fi

    TASK_NAME=$(basename "$TASK")
    log "Found task: $TASK_NAME — moving to doing/"
    mv "$TASK" "$DOING_DIR/$TASK_NAME"

    DOING_TASK="$DOING_DIR/$TASK_NAME"

    log "--- Executing $TASK_NAME ---"
    log "Task content:"
    cat "$DOING_TASK" >> "$LOG_FILE"
    echo "" >> "$LOG_FILE"

    # Hand the task to Claude Code via the claude CLI
    TASK_CONTENT=$(cat "$DOING_TASK")
    WORK_DIR="/Users/bytedance/Documents/github/ClawEvalkit"

    log "Invoking claude CLI for $TASK_NAME ..."
    cd "$WORK_DIR" && claude --dangerously-skip-permissions -p "$TASK_CONTENT" >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        log "$TASK_NAME completed successfully (exit $EXIT_CODE) — moving to done/"
    else
        log "$TASK_NAME finished with exit code $EXIT_CODE — moving to done/ (check log for errors)"
    fi

    mv "$DOING_TASK" "$DONE_DIR/$TASK_NAME"
    log "--- $TASK_NAME done ---"
done
