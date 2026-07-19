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

rdc repo delete my-app:experiment 2>/dev/null || true
rdc repo delete my-app 2>/dev/null || true
rdc repo create my-app --machine "$M" --size 2G
rdc repo admin template apply my-app --template app-postgres
rdc repo up my-app
rdc term connect my-app -c "echo 'Hello from production' > index.html" 2>/dev/null || true

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Fork the repo"
run_cmd "rdc repo fork my-app --tag experiment --up"

pause 2

section "Both repos exist side by side"
run_cmd "rdc repo list --machine $M"

pause 2

section "Original — index.html is here"
run_cmd "rdc term connect my-app -c 'ls -la index.html'"

pause 2

section "Fork — change something only in the fork"
run_cmd "rdc term connect my-app:experiment -c 'rm index.html && echo removed'"

pause 2

section "Original is untouched"
run_cmd "rdc term connect my-app -c 'ls -la index.html'"

pause 2

section "Clean up the fork"
run_cmd "rdc repo delete my-app:experiment"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Final cleanup
rdc repo down my-app 2>/dev/null || true
rdc repo down my-app --unmount 2>/dev/null || true
rdc repo delete my-app 2>/dev/null || true
