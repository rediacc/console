#!/bin/bash
# Tutorial 04: Creating Your First Repository
# Creates a 2 GB encrypted repository and lists it. The "Open in VS Code" step
# is omitted from the cast since it's an editor action; the docs cover that.
#
# Prerequisites: shared tutorial config + provisioned worker VM (from tutorial 03).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

M="$TUTORIAL_MACHINE_NAME"
C="--config tutorial"

# Pre-recording setup
rm -f ~/.config/rediacc/tutorial.json 2>/dev/null || true
rdc config init --name tutorial --ssh-key "$TUTORIAL_SSH_KEY"
rdc --config tutorial config machine add --name "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"
for i in $(seq 1 30); do
    ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
        "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" true 2>/dev/null && break
    sleep 2
done
rdc --config tutorial config machine setup --name "$M"
# Reap any orphaned repo state from previous tutorial runs.
rdc --config tutorial machine prune --name "$M" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true

# Make sure no leftover repo
rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true

clear_screen

section "Create an encrypted repository"
run_cmd "rdc $C repo create --name my-app -m $M --size 2G"

pause 2

section "List the repos on this machine"
run_cmd "rdc $C repo list -m $M"

pause 2

# Clean up
rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
