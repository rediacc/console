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
rdc config machine add --name "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"
for i in $(seq 1 30); do
    ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
        "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" true 2>/dev/null && break
    sleep 2
done
rdc config machine setup --name "$M"
# Reap any orphaned repo state from previous tutorial runs.
rdc machine prune --name "$M" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true

rdc repo delete --name my-app:experiment --machine "$M" 2>/dev/null || true
rdc repo delete --name my-app --machine "$M" 2>/dev/null || true
rdc repo create --name my-app --machine "$M" --size 2G
rdc repo template apply --name app-postgres --machine "$M" --repository my-app
rdc repo up --name my-app --machine "$M"
rdc term connect --machine "$M" --repository my-app --command "echo 'Hello from production' > index.html" 2>/dev/null || true

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Fork the repo"
run_cmd "rdc repo fork --parent my-app --machine $M --tag experiment --up"

pause 2

section "Both repos exist side by side"
run_cmd "rdc repo list --machine $M"

pause 2

section "Original — index.html is here"
run_cmd "rdc term connect --machine $M --repository my-app --command 'ls -la index.html' 2>/dev/null"

pause 2

section "Fork — change something only in the fork"
run_cmd "rdc term connect --machine $M --repository my-app:experiment --command 'rm index.html && echo removed' 2>/dev/null"

pause 2

section "Original is untouched"
run_cmd "rdc term connect --machine $M --repository my-app --command 'ls -la index.html' 2>/dev/null"

pause 2

section "Clean up the fork"
run_cmd "rdc repo delete --name my-app:experiment --machine $M"

pause 2

# Final cleanup
rdc repo down --name my-app --machine "$M" 2>/dev/null || true
rdc repo down --name my-app --machine "$M" --unmount 2>/dev/null || true
rdc repo delete --name my-app --machine "$M" 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
