#!/bin/bash
# Tutorial 12: Monitoring
# Demonstrates rdc machine status (system, containers, repos) and rdc doctor.
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
rdc machine add "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"
for i in $(seq 1 30); do
    ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
        "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" true 2>/dev/null && break
    sleep 2
done
rdc machine setup "$M"
# Reap any orphaned repo state from previous tutorial runs.
rdc machine prune "$M" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true

rdc repo delete my-app --yes 2>/dev/null || true
rdc repo create my-app --machine "$M" --size 2G
rdc repo admin template apply my-app --template app-postgres
rdc repo up my-app

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Health — system info"
run_cmd "rdc machine status $M --system"

pause 2

section "Containers"
run_cmd "rdc machine status $M --containers"

pause 2

section "Repos"
run_cmd "rdc machine status $M --repositories"

pause 2

section "Everything in one shot"
run_cmd "rdc machine status $M"

pause 2

section "Local sanity check"
run_cmd "rdc doctor"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Cleanup
rdc repo down my-app 2>/dev/null || true
rdc repo down my-app --unmount 2>/dev/null || true
rdc repo delete my-app --yes 2>/dev/null || true
