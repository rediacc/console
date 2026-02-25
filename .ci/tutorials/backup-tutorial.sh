#!/bin/bash
# Tutorial: Backup & Networking
# Records backup schedule configuration and infrastructure/networking setup.
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

clear_screen

section "Step 1: View current storages"
run_cmd "rdc $C config storages"

pause 2

section "Step 2: Configure backup schedule"
run_cmd "rdc $C backup schedule set --destination my-s3 --cron '0 2 * * *' --enable"

pause 2

section "Step 3: View backup schedule"
run_cmd "rdc $C backup schedule show"

pause 2

section "Step 4: Configure infrastructure"
run_cmd "rdc $C config set-infra $M --public-ipv4 $TUTORIAL_MACHINE_IP --base-domain test.local --cert-email admin@test.local"

pause 2

section "Step 5: Add TCP/UDP ports"
run_cmd "rdc $C config set-infra $M --tcp-ports 25,143,465,587,993 --udp-ports 53"

pause 2

section "Step 6: View infrastructure config"
run_cmd "rdc $C config show-infra $M"

pause 2

section "Step 7: Disable backup schedule"
run_cmd "rdc $C backup schedule set --disable"

pause 1

run_cmd "rdc $C backup schedule show"

pause 1

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
