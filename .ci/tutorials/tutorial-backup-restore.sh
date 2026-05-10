#!/bin/bash
# Tutorial 11: Backup & Restore
# Demonstrates rdc config storage import, rdc repo push, rdc repo backup list,
# and the machine-to-machine push variant. Uses a local rclone "alias" remote
# pointing at /tmp so the recording works without external storage.
#
# Prerequisites: shared tutorial config + provisioned worker VM. rclone
# installed locally (the import file uses an `alias` remote).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

M="$TUTORIAL_MACHINE_NAME"
BACKUP_HOST="${TUTORIAL_BACKUP_HOST:-192.168.111.12}"
BACKUP_USER="${TUTORIAL_BACKUP_USER:-$TUTORIAL_MACHINE_USER}"
C="--config tutorial"
RCLONE_CONF=/tmp/tutorial-rclone.conf

# Pre-recording setup
rm -f ~/.config/rediacc/tutorial.json 2>/dev/null || true
rdc config init --name tutorial --ssh-key "$TUTORIAL_SSH_KEY"
rdc --config tutorial config machine add --name "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"
for i in $(seq 1 30); do
    ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
        "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" true 2>/dev/null && break
    sleep 2
done
rdc --config tutorial config machine setup --name "$M"
# Reap any orphaned repo state from previous tutorial runs.
rdc --config tutorial machine prune --name "$M" --orphaned-repos --force --grace-days 0 --force-delete-mounted 2>/dev/null || true

rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true
rdc $C repo create --name my-app -m "$M" --size 2G
rdc $C repo template apply --name app-postgres -m "$M" -r my-app

# rclone config for the recording: sftp to a sibling VM in the test cluster.
# Real users would import their own production rclone.conf. The tutorial
# recording uses sftp because alias/local types are not in PROVIDER_MAPPING.
cat >"$RCLONE_CONF" <<EOF
[my-storage]
type = sftp
host = $BACKUP_HOST
user = $BACKUP_USER
key_file = $TUTORIAL_SSH_KEY
EOF

clear_screen

section "Step 1: Configure storage"
run_cmd "rdc $C config storage import --file $RCLONE_CONF"

pause 1

run_cmd "rdc $C config storage list"

pause 2

section "Step 2: Push a backup"
# Tolerate push errors: real backends will succeed; the recording's sftp
# target may have permission/path quirks. The command + output are what
# matters for the cast.
run_cmd "rdc $C repo push --name my-app -m $M --to my-storage || true"

pause 2

section "List the backups"
run_cmd "rdc $C repo backup list --from my-storage -m $M || true"

pause 2

# Cleanup
rdc $C repo down --name my-app -m "$M" 2>/dev/null || true
rdc $C repo down --name my-app -m "$M" --unmount 2>/dev/null || true
rdc $C repo delete --name my-app -m "$M" 2>/dev/null || true
rm -f "$RCLONE_CONF"

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
