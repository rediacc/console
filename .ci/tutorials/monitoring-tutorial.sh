#!/bin/bash
# Tutorial: Monitoring & Diagnostics
# Records the monitoring workflow: query, doctor, connectivity checks.
#
# Prerequisites:
#   - rdc CLI available in PATH (or TUTORIAL_RDC_CMD set)
#   - A provisioned machine (TUTORIAL_MACHINE_NAME) at TUTORIAL_MACHINE_IP
#   - Config "tutorial" with machine configured and a running repository

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

M="$TUTORIAL_MACHINE_NAME"
C="--config tutorial"

# Pre-recording setup (cleared by clear_screen below)
rm -f ~/.config/rediacc/tutorial.json 2>/dev/null || true
rdc config init --name tutorial --ssh-key "$TUTORIAL_SSH_KEY"
rdc --config tutorial config machine add --name "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"

clear_screen

section "Step 1: Run diagnostics"
run_cmd "rdc $C doctor || true"

pause 2

section "Step 2: System overview"
run_cmd "rdc $C machine query --name $M --system || true"

pause 2

section "Step 3: View running containers"
run_cmd "rdc $C machine query --name $M --containers"

pause 2

section "Step 4: Check systemd services"
run_cmd "rdc $C machine query --name $M --services"

pause 2

section "Step 5: Full machine status"
run_cmd "rdc $C machine query --name $M"

pause 2

section "Step 6: Scan host keys"
run_cmd "rdc $C config machine scan-keys -m $M"

pause 2

section "Step 7: Verify connectivity"
run_cmd "rdc $C term connect -m $M -c hostname"

pause 1

run_cmd "rdc $C term connect -m $M -c uptime"

pause 1

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
