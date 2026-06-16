#!/bin/bash
# Tutorial 10: Production Mode
# Demonstrates the dev → prod transition: rdc repo up (production), autostart
# enable, autostart list, rdc repo down. The "renet dev down" piece runs from
# inside the repo sandbox in the real flow; here we replicate it via
# `rdc term connect --command "renet dev down"` for a single-pass cast.
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
rdc config machine add --name "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"
for i in $(seq 1 30); do
    ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
        "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" true 2>/dev/null && break
    sleep 2
done
rdc config machine setup --name "$M"
# Reap any orphaned repo state from previous tutorial runs.
rdc machine prune --name "$M" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true

rdc repo delete --name my-app --machine "$M" 2>/dev/null || true
rdc repo create --name my-app --machine "$M" --size 2G
rdc repo template apply --name app-postgres --machine "$M" --repository my-app

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Start in production mode (detached)"
run_cmd "rdc repo up --name my-app --machine $M"

pause 2

section "Enable autostart — survive reboots"
run_cmd "rdc repo autostart enable --name my-app --machine $M"

pause 1

section "List autostart-enabled repos"
run_cmd "rdc repo autostart list --machine $M"

pause 2

section "Stopping the app from your laptop"
run_cmd "rdc repo down --name my-app --machine $M"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Cleanup
rdc repo autostart disable --name my-app --machine "$M" 2>/dev/null || true
rdc repo down --name my-app --machine "$M" --unmount 2>/dev/null || true
rdc repo delete --name my-app --machine "$M" 2>/dev/null || true
