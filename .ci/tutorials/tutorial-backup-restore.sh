#!/bin/bash
# Tutorial 11: Backup & Restore
# The full story: import an S3-compatible storage, push a backup, list it,
# then prove the restore path — take the repo offline, pull the backup back,
# and remount it.
#
# Prerequisites: shared tutorial config + provisioned worker VM + RustFS
# running on the bridge VM with the rediacc-test bucket (the record stage in
# run.sh starts it via `renet ops rustfs start`).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

# Silence pre-recording setup so its output doesn't bleed into the cast.
exec 3>&1 4>&2
exec >/dev/null 2>&1

M="$TUTORIAL_MACHINE_NAME"
# RustFS S3 endpoint — the bridge VM in the recording cluster. Credentials
# are the renet ops defaults (lab-only; see pkg/infra/config/config.go).
S3_ENDPOINT="${TUTORIAL_S3_ENDPOINT:-http://192.168.111.1:9000}"
S3_ACCESS_KEY="${TUTORIAL_S3_ACCESS_KEY:-rediacc-rustfs}"
S3_SECRET_KEY="${TUTORIAL_S3_SECRET_KEY:-rediacc-rustfs-secret-key}"
S3_BUCKET="${TUTORIAL_S3_BUCKET:-rediacc-test}"
RCLONE_CONF=/tmp/tutorial-rclone.conf

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

# rclone config for the recording: the RustFS S3 endpoint on the bridge VM.
# Real users import their own production rclone.conf (any S3-compatible
# provider, Backblaze B2, sftp, ... — every rclone backend works).
cat >"$RCLONE_CONF" <<EOF
[my-storage]
type = s3
provider = Other
endpoint = $S3_ENDPOINT
access_key_id = $S3_ACCESS_KEY
secret_access_key = $S3_SECRET_KEY
force_path_style = true
bucket = $S3_BUCKET
EOF

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Step 1: Configure storage"
run_cmd "rdc config storage import --file $RCLONE_CONF"

pause 1

run_cmd "rdc config storage list"

pause 2

section "Step 2: Push a backup"
run_cmd "rdc repo push --name my-app --machine $M --to my-storage"

pause 2

section "Step 3: List the backups"
run_cmd "rdc repo backup list --from my-storage --machine $M"

pause 2

section "Step 4: Restore — take the repo offline"
run_cmd "rdc repo down --name my-app --machine $M --unmount"

pause 1

section "Pull the backup back"
run_cmd "rdc repo pull --name my-app --machine $M --from my-storage --force --yes"

pause 1

section "Mount it again — restored"
run_cmd "rdc repo mount --name my-app --machine $M"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Cleanup
rdc repo down --name my-app --machine "$M" 2>/dev/null || true
rdc repo down --name my-app --machine "$M" --unmount 2>/dev/null || true
rdc repo delete --name my-app --machine "$M" 2>/dev/null || true
rm -f "$RCLONE_CONF"
