#!/bin/bash
# Tutorial 01: Installation
# Runs the real curl install (the script overwrites any existing rdc binary,
# so it's safe to re-run on a host that already has rdc), then verifies the
# install with rdc --version.
#
# Prerequisites:
#   - curl available
#   - network access to www.rediacc.com

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

clear_screen

section "Install the CLI"
# Real curl install. The install script overwrites the existing binary, so
# re-running on a host that already has rdc is fine — the freshly-installed
# binary is what the next command (rdc --version) invokes.
run_cmd "curl -fsSL https://www.rediacc.com/install.sh | bash"

pause 2

section "Confirm rdc is installed"
run_cmd "rdc --version"

pause 2

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
