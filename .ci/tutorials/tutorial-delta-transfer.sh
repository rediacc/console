#!/bin/bash
# Tutorial 17: Delta Transfer
# The first push to another machine copies the repository image in full —
# the pre-seeded gigabyte of data makes that visibly heavy. Every push
# after that transfers only the changed blocks — hands-free: the CLI
# keeps an immutable base on both machines and computes the delta. The
# push output prints the transferred bytes, so the full-vs-delta
# difference is on screen.
#
# Prerequisites: shared tutorial config + TWO provisioned worker VMs.

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

rdc repo delete --name my-app --machine "$M" 2>/dev/null || true
rdc repo delete --name my-app --machine "$M2" 2>/dev/null || true
rdc repo create --name my-app --machine "$M" --size 2G
rdc repo template apply --name app-postgres --machine "$M" --repository my-app
rdc repo up --name my-app --machine "$M"
# Seed a real gigabyte of data so the first push is visibly heavy and
# the second push's 50 MB delta is visibly NOT a full copy. `sync`
# settles the inner ext4 so the push sees the seeded blocks.
rdc term connect --machine "$M" --repository my-app \
    --command 'dd if=/dev/urandom of=dataset.bin bs=1M count=1024 status=none && sync'

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "First push — the full image travels"
run_cmd "rdc repo push --name my-app --machine $M --to $M2"

pause 2

section "Change a little data"
run_cmd "rdc term connect --machine $M --repository my-app --command 'dd if=/dev/urandom of=delta-test.bin bs=1M count=50 status=none && ls -lh delta-test.bin'" \
    "rdc term connect --machine $M --repository my-app --command 'dd if=/dev/urandom of=delta-test.bin bs=1M count=50 status=none && sync && ls -lh delta-test.bin'"

pause 2

section "Push again — only the changed blocks travel"
run_cmd "rdc repo push --name my-app --machine $M --to $M2"

pause 2

section "Same repo, both machines, seconds apart"
run_cmd "rdc repo list --machine $M2"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Cleanup
rdc repo delete --name my-app --machine "$M2" 2>/dev/null || true
rdc repo down --name my-app --machine "$M" 2>/dev/null || true
rdc repo down --name my-app --machine "$M" --unmount 2>/dev/null || true
rdc repo delete --name my-app --machine "$M" 2>/dev/null || true
