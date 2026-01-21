#!/bin/bash
# Create completion signal file for CI job coordination
# Usage: create-complete.sh --name <signal_name> [--output <dir>] [--status <status>]
#
# Creates a file that signals job completion. Used by backend job to wait
# for all platform tests to complete.
#
# Options:
#   --name    Signal name (e.g., "cli-Linux", "e2e-chromium")
#   --output  Output directory (default: RUNNER_TEMP or /tmp)
#   --status  Job status (success, failure, cancelled). Default: success
#
# Example:
#   .ci/scripts/signal/create-complete.sh --name "cli-Linux"
#   .ci/scripts/signal/create-complete.sh --name "cli-Linux" --status ${{ job.status }}

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

NAME="${ARG_NAME:-}"
OUTPUT_DIR="${ARG_OUTPUT:-$CI_TEMP}"
STATUS="${ARG_STATUS:-success}"

# Validate required arguments
if [[ -z "$NAME" ]]; then
    log_error "Usage: create-complete.sh --name <signal_name> [--output <dir>] [--status <status>]"
    exit 1
fi

# Create output directory if needed
mkdir -p "$OUTPUT_DIR"

# Create completion signal file with status
SIGNAL_FILE="$OUTPUT_DIR/complete-${NAME}.txt"
echo "$STATUS" > "$SIGNAL_FILE"

log_info "Created completion signal: $SIGNAL_FILE (status: $STATUS)"

# Also create a generic complete.txt for simple cases
echo "$STATUS" > "$OUTPUT_DIR/complete.txt"
