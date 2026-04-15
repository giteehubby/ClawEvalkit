#!/bin/bash
# Sync papers to linjh1118 private repo
# Usage: ./scripts/sync_papers.sh
#
# Note: papers/ is in .gitignore of ClawEvalkit, so it never appears in giteehubby.
# This script manages it as a separate git repo synced only to linjh1118.

PAPERS_DIR="results/papers/clawRecipe_emnlp_2027"
PRIVATE_REPO="git@ssh.github.com:linjh1118/ClawEvalkit.git"
BRANCH="main"

if [ ! -d "$PAPERS_DIR" ]; then
    echo "papers dir not found: $PAPERS_DIR"
    exit 1
fi

cd "$PAPERS_DIR"

# Initialize as a separate git repo if not already
if [ ! -d .git ]; then
    git init
    git remote add origin "$PRIVATE_REPO"
    git fetch origin
    git checkout -t origin/main 2>/dev/null || git checkout -b main
fi

# Remove any nested git repos
find . -name ".git" -type d | grep -v "^./.git$" | while read d; do rm -rf "$d"; done

git add -A
git commit -m "Sync papers $(date '+%Y-%m-%d %H:%M')" || echo "No new changes"
git push origin "$BRANCH"

echo "Done."
