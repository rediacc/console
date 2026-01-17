#!/bin/bash
# Create completion signal file for CI job coordination
# Usage: create-complete.sh --name <signal_name> [--output <dir>]
#
# Creates a file that signals job completion. Used by backend job to wait
# for all platform tests to complete.
#
# Options:
#   --name    Signal name (e.g., "cli-Linux", "e2e-chromium")
#   --output  Output directory (default: RUNNER_TEMP or /tmp)
#
# Example:
#   .ci/scripts/signal/create-complete.sh --name "cli-Linux"

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

NAME="${ARG_NAME:-}"
OUTPUT_DIR="${ARG_OUTPUT:-$CI_TEMP}"

# Validate required arguments
if [[ -z "$NAME" ]]; then
    log_error "Usage: create-complete.sh --name <signal_name> [--output <dir>]"
    exit 1
fi

# Create output directory if needed
mkdir -p "$OUTPUT_DIR"

# Create completion signal file
SIGNAL_FILE="$OUTPUT_DIR/complete-${NAME}.txt"
echo "complete" > "$SIGNAL_FILE"

log_info "Created completion signal: $SIGNAL_FILE"

# Also create a generic complete.txt for simple cases
echo "complete" > "$OUTPUT_DIR/complete.txt"
