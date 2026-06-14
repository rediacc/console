#!/bin/bash
# Tutorial 04: Creating Your First Repository
# Creates a 2 GB encrypted repository, lists it, and shows (without running) the
# VS Code command so viewers know they can open the repo in their editor.
#
# Prerequisites: shared tutorial config + provisioned worker VM (from tutorial 03).

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

# Make sure no leftover repo
rdc repo delete --name my-app --machine "$M" 2>/dev/null || true

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Create an encrypted repository"
run_cmd "rdc repo create --name my-app --machine $M --size 2G"

pause 2

section "List the repos on this machine"
run_cmd "rdc repo list --machine $M"

pause 2

section "Open it in VS Code (optional)"
# Type the command without running it — launching an editor isn't useful in a cast.
type_only_cmd "rdc vscode connect --machine $M --repository my-app"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Clean up
rdc repo delete --name my-app --machine "$M" 2>/dev/null || true
