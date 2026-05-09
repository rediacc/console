#!/bin/bash
# Tutorial 05: Deploying Your First App
# Demonstrates the template list / template apply / repo up flow. Uses a
# minimal local app (Rediaccfile + docker-compose.yml) staged at
# /tmp/tutorial-app/ rather than the app-postgres template, so the recording
# works even when external image pulls are slow.
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

clear_screen

section "Step 1: Pick — list the available templates"
run_cmd "rdc $C repo template list"

pause 2

section "Step 2: Apply a template"
run_cmd "rdc $C repo template apply --name app-postgres -m $M -r my-app"

pause 2

section "Step 3: Run — start the repo"
run_cmd "rdc $C repo up --name my-app -m $M"

pause 2

section "Verify what's running"
run_cmd "rdc $C term connect -m $M -r my-app -c 'docker ps'"

pause 2

# Clean up
rdc $C repo down --name my-app -m "$M" 2>/dev/null || true
rdc $C repo down --name my-app -m "$M" --unmount 2>/dev/null || true
rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
