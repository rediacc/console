#!/bin/bash
# Shared utilities for E2E Elite environment management

# Constants
ELITE_REPO="rediacc/elite"
WORKFLOW_NAME="Service Run"
E2E_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID_FILE="$E2E_DIR/.elite-run-id"
DEPLOYMENT_INFO_FILE="$E2E_DIR/.deployment-info.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ${NC} $*"
}

log_success() {
    echo -e "${GREEN}✓${NC} $*"
}

log_error() {
    echo -e "${RED}✗${NC} $*" >&2
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $*"
}

log_debug() {
    if [ "${DEBUG:-false}" = "true" ]; then
        echo -e "${BLUE}[DEBUG]${NC} $*"
    fi
}

# Check if required command exists
require_command() {
    local cmd="$1"
    if ! command -v "$cmd" &> /dev/null; then
        log_error "Required command '$cmd' not found"
        log_error "Please install $cmd to continue"
        exit 1
    fi
}

# Check all required dependencies
check_dependencies() {
    require_command gh
    require_command jq
    require_command curl
}

# Get current run ID
get_run_id() {
    if [ ! -f "$RUN_ID_FILE" ]; then
        log_error "No active Elite environment found"
        log_error "Run './go trigger' to start an environment"
        return 1
    fi
    cat "$RUN_ID_FILE"
}

# Save run ID
save_run_id() {
    local run_id="$1"
    echo "$run_id" > "$RUN_ID_FILE"
}

# Clear run ID
clear_run_id() {
    rm -f "$RUN_ID_FILE"
}

# Get deployment info
get_deployment_info() {
    if [ ! -f "$DEPLOYMENT_INFO_FILE" ]; then
        log_error "No deployment information found"
        log_error "Deployment info is downloaded during trigger"
        return 1
    fi
    cat "$DEPLOYMENT_INFO_FILE"
}

# Parse JSON value
jq_get() {
    local json="$1"
    local path="$2"
    echo "$json" | jq -r "$path"
}

# Cleanup trap handler
cleanup_on_exit() {
    log_debug "Cleanup handler called"
    # Add any cleanup logic here if needed
}

# Set up trap for cleanup
trap cleanup_on_exit EXIT

# Pretty print separator
print_separator() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Wait with spinner
wait_with_spinner() {
    local pid=$1
    local message="${2:-Waiting}"
    local spinner='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0

    while kill -0 $pid 2>/dev/null; do
        i=$(( (i+1) %10 ))
        printf "\r${BLUE}${spinner:$i:1}${NC} $message"
        sleep 0.1
    done
    printf "\r"
}

# Poll for condition with timeout
poll_until() {
    local check_cmd="$1"
    local timeout="${2:-300}"  # Default 5 minutes
    local interval="${3:-3}"   # Default 3 seconds
    local elapsed=0

    while ! eval "$check_cmd"; do
        if [ $elapsed -ge $timeout ]; then
            return 1
        fi
        sleep $interval
        elapsed=$((elapsed + interval))
    done
    return 0
}

# Export functions for use in scripts
export -f log_info log_success log_error log_warn log_debug
export -f require_command check_dependencies
export -f get_run_id save_run_id clear_run_id
export -f get_deployment_info jq_get
export -f print_separator wait_with_spinner poll_until
