#!/bin/bash
# Tutorial: Backup & Networking
# Records backup strategy configuration and infrastructure/networking setup.
#
# Prerequisites:
#   - rdc CLI available in PATH (or TUTORIAL_RDC_CMD set)
#   - A provisioned machine (TUTORIAL_MACHINE_NAME)
#   - Config "tutorial" with machine configured

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

M="$TUTORIAL_MACHINE_NAME"
C="--config tutorial"

# Pre-recording setup (cleared by clear_screen below)
rm -f ~/.config/rediacc/tutorial.json 2>/dev/null || true
rdc config init --name tutorial --ssh-key "$TUTORIAL_SSH_KEY"
rdc --config tutorial config machine add --name "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"

# Create an rclone config pointing to the local RustFS (S3-compatible) on the bridge VM
RCLONE_TMP="$(mktemp /tmp/tutorial-rclone-XXXXXX.conf)"
BRIDGE_IP="192.168.111.1"
cat >"$RCLONE_TMP" <<RCLONE
[my-s3]
type = s3
provider = Other
endpoint = http://${BRIDGE_IP}:9000
access_key_id = rustfsadmin
secret_access_key = rustfsadmin
RCLONE

clear_screen

section "Step 1: Import a storage backend"
run_cmd "rdc $C config storage import --file $RCLONE_TMP --name my-s3"

pause 1

run_cmd "rdc $C config storage list"

pause 2

section "Step 2: Configure backup strategy"
run_cmd "rdc $C config backup-strategy set --destination my-s3 --cron '0 2 * * *' --enable"

pause 2

section "Step 3: View backup strategy"
run_cmd "rdc $C config backup-strategy show"

pause 2

section "Step 4: Configure infrastructure"
run_cmd "rdc $C config infra set -m $M --public-ipv4 $TUTORIAL_MACHINE_IP --base-domain test.local --cert-email admin@test.local"

pause 2

section "Step 5: Add TCP/UDP ports"
run_cmd "rdc $C config infra set -m $M --tcp-ports 25,143,465,587,993 --udp-ports 53"

pause 2

section "Step 6: View infrastructure config"
run_cmd "rdc $C config infra show -m $M"

pause 2

section "Step 7: Disable backup strategy"
run_cmd "rdc $C config backup-strategy set --disable"

pause 1

run_cmd "rdc $C config backup-strategy show"

pause 1

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
