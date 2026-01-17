#!/bin/bash
# Shell script compatibility check using ShellCheck
# Used by both ./go quality shell and CI
#
# Checks all shell scripts for cross-platform compatibility issues
#
# Exclusions:
#   SC1091 - Not following sourced files (common.sh is sourced dynamically)
#   SC2034 - Variable appears unused (false positive for exported constants)

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

# ShellCheck options
# -e SC1090: Can't follow non-constant source (dynamic sourcing)
# -e SC1091: Not following sourced files (dynamic sourcing)
# -e SC2034: Ignore "appears unused" (false positive for exported constants)
# -S warning: Only fail on warnings or errors (not info/style)
SHELLCHECK_OPTS="-e SC1090 -e SC1091 -e SC2034 -S warning"

main() {
    cd "$ROOT_DIR"

    log_info "Checking shell script compatibility"

    # Verify shellcheck is installed
    if ! command -v shellcheck &>/dev/null; then
        log_error "shellcheck is not installed"
        log_info "Install with: apt install shellcheck (Ubuntu) or brew install shellcheck (macOS)"
        exit 1
    fi

    shellcheck --version

    # Check all shell scripts in .ci directory
    log_info "Checking .ci/**/*.sh"
    # shellcheck disable=SC2086
    find .ci -name "*.sh" -type f -exec shellcheck $SHELLCHECK_OPTS {} +

    # Check the main go script
    log_info "Checking ./go"
    # shellcheck disable=SC2086
    shellcheck $SHELLCHECK_OPTS ./go

    log_success "Shell scripts passed"
}

main "$@"
