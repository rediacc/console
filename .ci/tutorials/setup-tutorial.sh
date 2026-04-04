#!/bin/bash
# Tutorial: Machine Setup & Configuration
# Records the complete workflow: config init, add machine, infra config, diagnostics.
#
# Prerequisites:
#   - rdc CLI available in PATH (or TUTORIAL_RDC_CMD set)
#   - A reachable server (TUTORIAL_MACHINE_IP) with SSH access
#   - SSH key at TUTORIAL_SSH_KEY

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

# Clean up any previous tutorial config so we start fresh
rm -f ~/.config/rediacc/tutorial-demo.json 2>/dev/null || true

clear_screen

section "Step 1: Create a new config"
run_cmd "rdc config init --name tutorial-demo --ssh-key $TUTORIAL_SSH_KEY"

pause 1

section "Step 2: View configs"
run_cmd "rdc config list"

pause 2

section "Step 3: Add a machine"
run_cmd "rdc --config tutorial-demo config machine add --name $TUTORIAL_MACHINE_NAME --ip $TUTORIAL_MACHINE_IP --user $TUTORIAL_MACHINE_USER"

pause 2

section "Step 4: View machines"
run_cmd "rdc --config tutorial-demo config machine list"

pause 2

section "Step 5: Test connectivity"
run_cmd "rdc --config tutorial-demo term connect -m $TUTORIAL_MACHINE_NAME -c hostname"

pause 1

run_cmd "rdc --config tutorial-demo term connect -m $TUTORIAL_MACHINE_NAME -c uptime"

pause 2

section "Step 6: Run diagnostics"
run_cmd "rdc --config tutorial-demo doctor || true"

pause 2

section "Step 7: Configure infrastructure"
run_cmd "rdc --config tutorial-demo config infra set -m $TUTORIAL_MACHINE_NAME --public-ipv4 $TUTORIAL_MACHINE_IP --base-domain test.local --cert-email admin@test.local"

pause 1

run_cmd "rdc --config tutorial-demo config infra show -m $TUTORIAL_MACHINE_NAME"

pause 2

# Clean up the tutorial config
rm -f ~/.config/rediacc/tutorial-demo.json 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
