#!/bin/bash
# Tutorial 16: Live Migration
# Move a running repository — containers, database, process memory — from
# one machine to another with rdc repo migrate --checkpoint. The app keeps
# an in-memory counter; after the migration the counter CONTINUES on the
# new machine instead of resetting to 1. That is process memory making
# the trip, not just disk.
#
# Prerequisites: shared tutorial config + TWO provisioned worker VMs
# (TUTORIAL_MACHINE_IP and TUTORIAL_BACKUP_HOST, as exported by run.sh).
# The CRIU-compatible demo app ships in .ci/tutorials/apps/heartbeat/.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

# Silence pre-recording setup so its output doesn't bleed into the cast.
exec 3>&1 4>&2
exec >/dev/null 2>&1

M="$TUTORIAL_MACHINE_NAME"
M2="${TUTORIAL_MACHINE2_NAME:-machine-12}"
M2_IP="${TUTORIAL_BACKUP_HOST:-192.168.111.12}"
M2_USER="${TUTORIAL_BACKUP_USER:-$TUTORIAL_MACHINE_USER}"
APP_DIR="$SCRIPT_DIR/apps/heartbeat"

# Pre-recording setup
rm -f ~/.config/rediacc/rediacc.json 2>/dev/null || true
rdc config init --ssh-key "$TUTORIAL_SSH_KEY"
rdc config machine add --name "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"
rdc config machine add --name "$M2" --ip "$M2_IP" --user "$M2_USER"
for ip in "$TUTORIAL_MACHINE_IP" "$M2_IP"; do
    for i in $(seq 1 30); do
        ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
            "$TUTORIAL_MACHINE_USER@$ip" true 2>/dev/null && break
        sleep 2
    done
done
rdc config machine setup --name "$M"
rdc config machine setup --name "$M2"
rdc machine prune --name "$M" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true
rdc machine prune --name "$M2" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true

rdc repo delete --name pulse --machine "$M" 2>/dev/null || true
rdc repo delete --name pulse --machine "$M2" 2>/dev/null || true
rdc repo create --name pulse --machine "$M" --size 2G
rdc repo sync upload --machine "$M" --repository pulse --local "$APP_DIR/"
rdc repo up --name pulse --machine "$M"
# Wait until the heartbeat app is actually beating (postgres healthy +
# npm install done + first beats written) so the opening shot shows a
# live counter.
for i in $(seq 1 60); do
    rdc term connect --machine "$M" --repository pulse \
        --command 'docker logs heartbeat_app 2>&1 | grep -q "memory counter=3"' 2>/dev/null && break
    sleep 3
done

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "A live app — its in-memory counter is beating"
run_cmd "rdc term connect --machine $M --repository pulse --command 'docker logs heartbeat_app --tail 5'"

pause 2

section "Migrate it to another machine — live, memory included"
run_cmd "rdc repo migrate --name pulse --from $M --to $M2 --checkpoint --skip-dns"

pause 2

section "It now runs on the new machine"
run_cmd "rdc repo list --machine $M2"

pause 2

section "The source: stopped and unmounted — nothing runs here"
run_cmd "rdc repo list --machine $M"

pause 2

section "The counter CONTINUED — process memory made the trip"
run_cmd "rdc term connect --machine $M2 --repository pulse --command 'docker logs heartbeat_app --tail 5'"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Cleanup
rdc repo down --name pulse --machine "$M2" --unmount 2>/dev/null || true
rdc repo delete --name pulse --machine "$M2" 2>/dev/null || true
rdc repo delete --name pulse --machine "$M" 2>/dev/null || true
rdc config repository remove --name pulse:latest 2>/dev/null || true
