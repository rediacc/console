#!/bin/bash
# Tutorial 07: Forking a Repository
# Demonstrates rdc repo fork: instant clone, isolation, cleanup. We compress
# the prompter's verification flow (which spans multiple VS Code switches) by
# running each verification step from `rdc term connect -c`.
#
# Prerequisites: shared tutorial config + provisioned worker VM.

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

rdc $C repo delete --name my-app:experiment -m "$M" 2>/dev/null || true
rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true
rdc $C repo create --name my-app -m "$M" --size 2G
rdc $C repo template apply --name app-postgres -m "$M" -r my-app
rdc $C repo up --name my-app -m "$M"
rdc $C term connect -m "$M" -r my-app -c "echo 'Hello from production' > index.html" 2>/dev/null || true

clear_screen

section "Fork the repo"
run_cmd "rdc $C repo fork --parent my-app -m $M --tag experiment --up"

pause 2

section "Both repos exist side by side"
run_cmd "rdc $C repo list -m $M"

pause 2

section "Original — index.html is here"
run_cmd "rdc $C term connect -m $M -r my-app -c 'ls -la index.html'"

pause 2

section "Fork — change something only in the fork"
run_cmd "rdc $C term connect -m $M -r my-app:experiment -c 'rm index.html && echo removed'"

pause 2

section "Original is untouched"
run_cmd "rdc $C term connect -m $M -r my-app -c 'ls -la index.html'"

pause 2

section "Clean up the fork"
run_cmd "rdc $C repo delete --name my-app:experiment -m $M"

pause 2

# Final cleanup
rdc $C repo down --name my-app -m "$M" 2>/dev/null || true
rdc $C repo down --name my-app -m "$M" --unmount 2>/dev/null || true
rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
