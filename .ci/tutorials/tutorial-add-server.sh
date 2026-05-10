#!/bin/bash
# Tutorial 03: Adding Your First Server
# Creates a tutorial config, registers the worker VM, provisions renet, and
# shows where the config file lives.
#
# Prerequisites:
#   - rdc CLI available in PATH (or TUTORIAL_RDC_CMD set)
#   - A reachable server at TUTORIAL_MACHINE_IP with SSH access using TUTORIAL_SSH_KEY

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

M="$TUTORIAL_MACHINE_NAME"
rm -f ~/.config/rediacc/tutorial.json 2>/dev/null || true

clear_screen

section "Step 1: Register the server"
run_cmd "rdc config init --name tutorial --ssh-key $TUTORIAL_SSH_KEY"

pause 1

run_cmd "rdc --config tutorial config machine add --name $M --ip $TUTORIAL_MACHINE_IP --user $TUTORIAL_MACHINE_USER"

pause 2

# Wait for SSH to be ready before machine setup
for i in $(seq 1 30); do
    ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
        "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" true 2>/dev/null && break
    sleep 2
done

section "Step 2: Provision the server"
run_cmd "rdc --config tutorial config machine setup --name $M"

pause 2

section "Where the config lives"
run_cmd "rdc --config tutorial config show"

pause 2

run_cmd "ls -la ~/.config/rediacc/tutorial.json"

pause 2

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
