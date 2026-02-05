#!/bin/bash
# Shell script formatting check using shfmt
# Used by both ./run.sh quality shell and CI
#
# Checks all shell scripts for consistent formatting

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Colors (disabled in CI)
if [[ "${CI:-}" == "true" ]]; then
    RED="" GREEN="" NC=""
else
    RED='\033[0;31m' GREEN='\033[0;32m' NC='\033[0m'
fi

log_error() { echo -e "${RED}error: $1${NC}" >&2; }
log_success() { echo -e "${GREEN}success: $1${NC}"; }
log_info() { echo "info: $1"; }

# shfmt options
# -i 4: 4-space indentation
# -ci: indent switch cases
# -d: diff mode (show what would change, exit non-zero if changes needed)
SHFMT_OPTS="-i 4 -ci -d"

main() {
    cd "$ROOT_DIR"

    log_info "Checking shell script formatting"

    # Verify shfmt is installed
    if ! command -v shfmt &>/dev/null; then
        log_error "shfmt is not installed"
        log_info "Install with: go install mvdan.cc/sh/v3/cmd/shfmt@latest"
        log_info "Or: brew install shfmt (macOS) / apt install shfmt (Ubuntu)"
        exit 1
    fi

    shfmt --version

    # Check all shell scripts in .ci directory
    log_info "Checking .ci/**/*.sh"
    # shellcheck disable=SC2086
    find .ci -name "*.sh" -type f -exec shfmt $SHFMT_OPTS {} +

    # Check the main run.sh script
    log_info "Checking ./run.sh"
    # shellcheck disable=SC2086
    shfmt $SHFMT_OPTS ./run.sh

    # Check scripts/dev directory if it exists
    if [[ -d "scripts/dev" ]]; then
        log_info "Checking scripts/dev/**/*.sh"
        # shellcheck disable=SC2086
        find scripts/dev -name "*.sh" -type f -exec shfmt $SHFMT_OPTS {} +
    fi

    log_success "Shell script formatting passed"
}

main "$@"
