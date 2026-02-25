#!/bin/bash
# Tutorial: Getting Started with rdc ops
# Records the complete local VM provisioning workflow.
#
# Prerequisites: rdc CLI available in PATH, KVM/libvirt configured.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

clear_screen

section "Step 1: Verify system requirements"
run_cmd "rdc ops check"

pause 2

section "Step 2: Provision a minimal VM cluster"
run_cmd "rdc ops up --basic --skip-orchestration"

pause 2

section "Step 3: Check cluster status"
run_cmd "rdc ops status"

pause 2

section "Step 4: Run a command on the bridge VM"
run_cmd "rdc ops ssh 1 hostname"

pause 1

run_cmd "rdc ops ssh 1 uname -a"

pause 2

section "Step 5: Tear down the cluster"
run_cmd "rdc ops down"

pause 1

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
