#!/bin/bash
# Tutorial 02: SSH Key Configuration
# SSH keys are purely about local<->remote machine access — they have nothing to
# do with rdc. We generate a key and authorize it on the two example servers
# (192.168.111.11 and .12) with ssh-copy-id.
#
# Prerequisites:
#   - The example servers (192.168.111.11, 192.168.111.12) are reachable over SSH
#     (provisioned as part of the recording cluster).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

# Silence pre-recording setup so its output doesn't bleed into the cast.
exec 3>&1 4>&2
exec >/dev/null 2>&1

DEMO_KEY=/tmp/tutorial-id_ed25519
rm -f "$DEMO_KEY" "$DEMO_KEY.pub" 2>/dev/null || true

# Restore stdout/stderr so asciinema captures only the demo from here on.
exec >&3 2>&4

clear_screen

section "Step 1: Generate an SSH key"
run_cmd "ssh-keygen -t ed25519 -f $DEMO_KEY -N '' -q"

pause 2

section "Step 2: Authorize the key on your first server"
# ssh-copy-id appends the new public key to the server's authorized_keys.
run_cmd "ssh-copy-id -i $DEMO_KEY.pub -o StrictHostKeyChecking=no $TUTORIAL_MACHINE_USER@192.168.111.11"

pause 2

section "Step 3: Authorize it on your second server"
run_cmd "ssh-copy-id -i $DEMO_KEY.pub -o StrictHostKeyChecking=no $TUTORIAL_MACHINE_USER@192.168.111.12"

pause 2

# End the on-camera portion; cleanup below is not recorded.
end_recording
# Cleanup
rm -f "$DEMO_KEY" "$DEMO_KEY.pub" 2>/dev/null || true
