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

clear_screen

section "Step 1: Create an encrypted repository"
run_cmd "rdc $C repo create test-app -m $M --size 2G"

pause 2

section "Step 2: List repositories"
run_cmd "rdc $C repo list -m $M"

pause 2

section "Step 3: Upload application files"
# Pre-stage files via SSH (non-interactive)
scp -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no -q /tmp/tutorial-app/Rediaccfile /tmp/tutorial-app/docker-compose.yml "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP:/tmp/" 2>/dev/null
ssh -i "$TUTORIAL_SSH_KEY" -o StrictHostKeyChecking=no "$TUTORIAL_MACHINE_USER@$TUTORIAL_MACHINE_IP" "sudo cp /tmp/Rediaccfile /tmp/docker-compose.yml /mnt/rediacc/mounts/test-app/ && sudo chown rediacc:rediacc /mnt/rediacc/mounts/test-app/Rediaccfile /mnt/rediacc/mounts/test-app/docker-compose.yml" 2>/dev/null
run_cmd "rdc $C term $M -c 'ls -la /mnt/rediacc/mounts/test-app/'"

pause 2

section "Step 4: Start services"
run_cmd "rdc $C repo up test-app -m $M --mount"

pause 2

section "Step 5: View running containers"
run_cmd "rdc $C machine containers $M"

pause 2

section "Step 6: Access the repo via terminal"
run_cmd "rdc $C term $M test-app -c 'docker ps'"

pause 2

section "Step 7: Stop and clean up"
run_cmd "rdc $C repo down test-app -m $M"

pause 1

run_cmd "rdc $C repo unmount test-app -m $M"

pause 1

run_cmd "rdc $C repo delete test-app -m $M"

pause 1

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
