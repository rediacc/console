#!/bin/bash
# Tutorial 02: SSH Key Configuration
# Generates a tutorial-scoped SSH key and registers it with rdc. The real
# `ssh-copy-id` step is shown via echo because it requires an interactive
# password prompt that can't be automated in a recording.
#
# Prerequisites:
#   - rdc CLI available in PATH (or TUTORIAL_RDC_CMD set)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

DEMO_KEY=/tmp/tutorial-id_ed25519
rm -f "$DEMO_KEY" "$DEMO_KEY.pub" 2>/dev/null || true
rm -f ~/.config/rediacc/tutorial.json 2>/dev/null || true

clear_screen

section "Step 1: Generate an SSH key"
run_cmd "ssh-keygen -t ed25519 -f $DEMO_KEY -N '' -q"

pause 2

section "Step 2: Copy it to your server"
# Real ssh-copy-id needs an interactive password prompt. Show the command without running it.
run_cmd "echo 'ssh-copy-id -i $DEMO_KEY user@your-server-ip'"

pause 2

section "Step 3: Register the key with rdc"
run_cmd "rdc config init --name tutorial --ssh-key $DEMO_KEY"

pause 1

run_cmd "rdc --config tutorial config show"

pause 2

# Cleanup
rm -f "$DEMO_KEY" "$DEMO_KEY.pub" 2>/dev/null || true
rm -f ~/.config/rediacc/tutorial.json 2>/dev/null || true

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
