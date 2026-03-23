#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

cat > "$WORKSPACE/git_commands.sh" << 'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

# Operation 1: Create a new feature branch for the login functionality
git checkout -b feature-login

# Operation 2: Stage all changes and commit with the specified message
git add .
git commit -m "Add login page"

# Operation 3: Tag the current commit as version 1.0.0
git tag v1.0.0

echo "All git operations completed successfully."
SCRIPT

chmod +x "$WORKSPACE/git_commands.sh"
echo "Created git_commands.sh in $WORKSPACE"
