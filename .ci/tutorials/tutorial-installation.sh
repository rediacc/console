#!/bin/bash
# Tutorial 01: Installation
# Demonstrates the rdc install verification flow. The actual `curl install.sh | bash`
# step is skipped during recording — it can't be safely re-run in the host that
# already has rdc available. We exercise the verification commands the prompter
# walks through after install.
#
# Prerequisites:
#   - rdc CLI available in PATH (or TUTORIAL_RDC_CMD set)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/tutorial-helpers.sh"

clear_screen

section "Confirm rdc is installed"
run_cmd "rdc --version"

pause 2

section "Verify the install"
# `rdc doctor` exits non-zero when any check is `fail` (e.g. dev-mode CLIs
# don't have a valid subscription). Tolerate it -- the cast captures the
# full report regardless.
run_cmd "rdc doctor || true"

pause 2

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
