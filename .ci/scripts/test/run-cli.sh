#!/bin/bash
# Run CLI integration tests
# Usage: run-cli.sh [--filter <pattern>]
#
# Options:
#   --filter  Filter tests by pattern

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

FILTER="${ARG_FILTER:-}"

# Change to repo root
cd "$(get_repo_root)"

CLI_DIR="packages/cli"

log_step "Running CLI integration tests..."

CMD="npm test"
if [[ -n "$FILTER" ]]; then
    CMD="$CMD -- --grep \"$FILTER\""
fi

if (cd "$CLI_DIR" && $CMD); then
    log_info "CLI tests passed"
else
    log_error "CLI tests failed"
    exit 1
fi
