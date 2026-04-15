#!/bin/bash
# Sync papers to linjh1118 private repo
# Usage: ./scripts/sync_papers.sh
#
# Note: papers/ is in .gitignore, so it never goes to giteehubby.
# This script manages it as a separate git repo synced only to linjh1118.

PAPERS_DIR="results/papers/clawRecipe_emnlp_2027"
PRIVATE_REPO="git@github.com:linjh1118/ClawEvalkit.git"
BRANCH="main"

if [ ! -d "$PAPERS_DIR" ]; then
    echo "papers dir not found: $PAPERS_DIR"
    exit 1
fi

cd "$PAPERS_DIR"

# Initialize as a separate git repo if not already
if [ ! -d .git ]; then
    git init
    git add -A
    git commit -m "Initial commit"
fi

git add -A
git commit -m "Sync papers $(date '+%Y-%m-%d %H:%M')" || echo "No new changes"
git push "$PRIVATE_REPO" "$BRANCH"

echo "Done."
