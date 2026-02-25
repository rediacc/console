#!/bin/bash
# Tutorial: Tools — Terminal, File Sync, VS Code
# Records the tools workflow: term, sync, vscode, update.
#
# Prerequisites:
#   - rdc CLI available in PATH (or TUTORIAL_RDC_CMD set)
#   - A provisioned machine (TUTORIAL_MACHINE_NAME) with a running repository
#   - Config "tutorial" with machine and repo configured

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

M="$TUTORIAL_MACHINE_NAME"
C="--config tutorial"

clear_screen

section "Step 1: Connect to a machine"
run_cmd "rdc $C term $M -c hostname"

pause 1

run_cmd "rdc $C term $M -c uptime"

pause 2

section "Step 2: Connect to a repository"
run_cmd "rdc $C term $M test-app -c 'docker ps'"

pause 2

section "Step 3: Preview file sync (dry-run)"
run_cmd "rdc $C sync upload -m $M -r test-app --local /tmp/tutorial-app --dry-run"

pause 2

section "Step 4: Upload files"
run_cmd "rdc $C sync upload -m $M -r test-app --local /tmp/tutorial-app"

pause 2

section "Step 5: Verify uploaded files"
run_cmd "rdc $C term $M test-app -c 'ls -la'"

pause 2

section "Step 6: VS Code integration check"
run_cmd "rdc $C vscode check"

pause 2

section "Step 7: Check for CLI updates"
run_cmd "rdc update --check-only || true"

pause 1

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
