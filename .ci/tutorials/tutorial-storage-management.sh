#!/bin/bash
# Tutorial 18: Storage Management
# Never run out of disk: watch storage health, grow a repository online
# with zero downtime, reclaim freed blocks with trim, then hand the whole
# job to a policy so the machine does it automatically from now on.
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

rdc repo delete data-app 2>/dev/null || true
rdc repo create data-app --machine "$M" --size 2G
rdc repo admin template apply data-app --template app-postgres
rdc repo up data-app

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "The repo is filling up"
run_cmd "rdc term connect data-app -c 'dd if=/dev/zero of=big.bin bs=1M count=1200 status=none && df -h .'"

pause 2

section "Grow it online — zero downtime"
run_cmd "rdc repo expand data-app --size 4G"

pause 1

run_cmd "rdc term connect data-app -c 'df -h .'"

pause 2

section "Delete data, then give the blocks back to the pool"
run_cmd "rdc term connect data-app -c 'rm big.bin && df -h .'"

pause 1

run_cmd "rdc repo trim data-app"

pause 2

section "Now make the machine do all of this automatically"
run_cmd "rdc repo policy set data-app --auto-grow true --max-quota 8G --grow-step 25% --auto-trim true"

pause 1

run_cmd "rdc repo policy get data-app"

pause 2

section "The health view that ties it together"
run_cmd "rdc machine status $M --storage-health"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Cleanup
rdc repo down data-app 2>/dev/null || true
rdc repo down data-app --unmount 2>/dev/null || true
rdc repo delete data-app 2>/dev/null || true
