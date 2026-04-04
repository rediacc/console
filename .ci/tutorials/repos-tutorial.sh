#!/bin/bash
# Tutorial: Repository Lifecycle
# Records the complete workflow: create repo, deploy app, manage containers, clean up.
#
# Prerequisites:
#   - rdc CLI available in PATH (or TUTORIAL_RDC_CMD set)
#   - A provisioned machine (TUTORIAL_MACHINE_NAME) at TUTORIAL_MACHINE_IP
#   - Config "tutorial" with machine configured and renet path set
#   - Test app files at /tmp/tutorial-app/ (Rediaccfile + docker-compose.yml)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

M="$TUTORIAL_MACHINE_NAME"
C="--config tutorial"

# Pre-recording setup (cleared by clear_screen below)
rm -f ~/.config/rediacc/tutorial.json 2>/dev/null || true
rdc config init --name tutorial --ssh-key "$TUTORIAL_SSH_KEY"
rdc --config tutorial config machine add --name "$M" --ip "$TUTORIAL_MACHINE_IP" --user "$TUTORIAL_MACHINE_USER"

# Wait for SSH to be ready before running machine setup
for i in $(seq 1 30); do
    ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=2 \
        "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" true 2>/dev/null && break
    sleep 2
done

rdc --config tutorial config machine setup --name "$M"

clear_screen

section "Step 1: Create an encrypted repository"
run_cmd "rdc $C repo create --name test-app -m $M --size 2G"

pause 2

section "Step 2: List repositories"
run_cmd "rdc $C repo list -m $M"

pause 2

section "Step 3: Upload application files"
run_cmd "rdc $C repo sync upload -m $M -r test-app --local /tmp/tutorial-app"

pause 1

run_cmd "rdc $C term connect -m $M -r test-app -c 'ls -la'"

pause 2

section "Step 4: Start services"
run_cmd "rdc $C repo up --name test-app -m $M"

pause 2

section "Step 5: View running containers"
run_cmd "rdc $C machine query --name $M --containers"

pause 2

section "Step 6: Access the repo via terminal"
run_cmd "rdc $C term connect -m $M -r test-app -c 'docker ps'"

pause 2

section "Step 7: Stop and clean up"
run_cmd "rdc $C repo down --name test-app -m $M"

pause 1

run_cmd "rdc $C repo down --name test-app -m $M --unmount"

pause 1

run_cmd "rdc $C repo delete --name test-app -m $M"

pause 1

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
