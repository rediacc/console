#!/bin/bash
# Tutorial 10: Production Mode
# Demonstrates the dev → prod transition: rdc repo up (production), autostart
# enable, autostart list, rdc repo down. The "renet dev down" piece runs from
# inside the repo sandbox in the real flow; here we replicate it via
# `rdc term connect -c "renet dev down"` for a single-pass cast.
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

rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true
rdc $C repo create --name my-app -m "$M" --size 2G
rdc $C repo template apply --name app-postgres -m "$M" -r my-app

clear_screen

section "Start in production mode (detached)"
run_cmd "rdc $C repo up --name my-app -m $M"

pause 2

section "Enable autostart — survive reboots"
run_cmd "rdc $C repo autostart enable --name my-app -m $M"

pause 1

section "List autostart-enabled repos"
run_cmd "rdc $C repo autostart list -m $M"

pause 2

section "Stopping the app from your laptop"
run_cmd "rdc $C repo down --name my-app -m $M"

pause 2

# Cleanup
rdc $C repo autostart disable --name my-app -m "$M" 2>/dev/null || true
rdc $C repo down --name my-app -m "$M" --unmount 2>/dev/null || true
rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
