#!/bin/bash
# Tutorial: Tools -- Terminal, File Sync, VS Code
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

# Pre-recording setup (cleared by clear_screen below)
rm -f ~/.config/rediacc/tutorial.json 2>/dev/null || true
rdc config init --name tutorial --ssh-key "$TUTORIAL_SSH_KEY"
rdc --config tutorial config machine add --name "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"

# Wait for SSH + setup datastore + create test-app repo (needed for repo-context steps)
for i in $(seq 1 30); do
    ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
        "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" true 2>/dev/null && break
    sleep 2
done
rdc --config tutorial config machine setup --name "$M"
rdc --config tutorial repo create --name test-app -m "$M" --size 2G
rdc --config tutorial repo sync upload -m "$M" -r test-app --local /tmp/tutorial-app
rdc --config tutorial repo up --name test-app -m "$M"

clear_screen

section "Step 1: Connect to a machine"
run_cmd "rdc $C term connect -m $M -c hostname"

pause 1

run_cmd "rdc $C term connect -m $M -c uptime"

pause 2

section "Step 2: Connect to a repository"
run_cmd "rdc $C term connect -m $M -r test-app -c 'docker ps'"

pause 2

section "Step 3: Preview file sync (dry-run)"
run_cmd "rdc $C repo sync upload -m $M -r test-app --local /tmp/tutorial-app --dry-run"

pause 2

section "Step 4: Upload files"
run_cmd "rdc $C repo sync upload -m $M -r test-app --local /tmp/tutorial-app"

pause 2

section "Step 5: Verify uploaded files"
run_cmd "rdc $C term connect -m $M -r test-app -c 'ls -la'"

pause 2

section "Step 6: VS Code integration check"
run_cmd "rdc $C vscode check"

pause 2

section "Step 7: Check for CLI updates"
run_cmd "rdc update --check-only || true"

pause 1

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
