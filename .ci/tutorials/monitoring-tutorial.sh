#!/bin/bash
# Tutorial: Monitoring & Diagnostics
# Records the monitoring workflow: health, containers, services, vault-status, doctor.
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

clear_screen

section "Step 1: Run diagnostics"
run_cmd "rdc $C doctor || true"

pause 2

section "Step 2: Machine health check"
run_cmd "rdc $C machine health $M || true"

pause 2

section "Step 3: View running containers"
run_cmd "rdc $C machine containers $M"

pause 2

section "Step 4: Check systemd services"
run_cmd "rdc $C machine services $M"

pause 2

section "Step 5: Vault status overview"
run_cmd "rdc $C machine vault-status $M"

pause 2

section "Step 6: Scan host keys"
run_cmd "rdc $C config scan-keys $M"

pause 2

section "Step 7: Verify connectivity"
run_cmd "rdc $C term $M -c hostname"

pause 1

run_cmd "rdc $C term $M -c uptime"

pause 1

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
