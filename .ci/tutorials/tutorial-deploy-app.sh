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

# Silence pre-recording setup so its output doesn't bleed into the cast.
exec 3>&1 4>&2
exec >/dev/null 2>&1

M="$TUTORIAL_MACHINE_NAME"

# Pre-recording setup
rm -f ~/.config/rediacc/rediacc.json 2>/dev/null || true
rdc config init --ssh-key "$TUTORIAL_SSH_KEY"
rdc machine add "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"
for i in $(seq 1 30); do
    ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
        "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" true 2>/dev/null && break
    sleep 2
done
rdc machine setup "$M"
# Reap any orphaned repo state from previous tutorial runs.
rdc machine prune "$M" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true

rdc repo delete my-app 2>/dev/null || true
rdc repo create my-app --machine "$M" --size 2G

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Step 1: Pick — list the available templates"
run_cmd "rdc repo admin template list"

pause 2

section "Step 2: Apply a template"
run_cmd "rdc repo admin template apply my-app --template app-postgres"

pause 2

section "See what the template added"
run_cmd "rdc term connect my-app -c 'ls -la'"

pause 2

section "Step 3: Run — start the repo"
run_cmd "rdc repo up my-app"

pause 2

section "Verify what's running"
run_cmd "rdc term connect my-app -c 'docker ps'"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Clean up
rdc repo down my-app 2>/dev/null || true
rdc repo down my-app --unmount 2>/dev/null || true
rdc repo delete my-app 2>/dev/null || true
