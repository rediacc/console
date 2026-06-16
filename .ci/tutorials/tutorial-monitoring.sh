#!/bin/bash
# Tutorial 12: Monitoring
# Demonstrates rdc machine health, containers, repos, query, and rdc doctor.
# Brings up a small repo first so the queries return non-trivial data.
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
rdc repo up --name my-app --machine "$M"

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Health — system info"
run_cmd "rdc machine query --name $M --system"

pause 2

section "Containers"
run_cmd "rdc machine query --name $M --containers"

pause 2

section "Repos"
run_cmd "rdc machine query --name $M --repositories"

pause 2

section "Everything in one shot"
run_cmd "rdc machine query --name $M"

pause 2

section "Local sanity check"
run_cmd "rdc doctor"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Cleanup
rdc repo down --name my-app --machine "$M" 2>/dev/null || true
rdc repo down --name my-app --machine "$M" --unmount 2>/dev/null || true
rdc repo delete --name my-app --machine "$M" 2>/dev/null || true
