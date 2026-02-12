#!/bin/bash
# Check shell scripts for commands not available in minimal CI environments
#
# This complements shellcheck by verifying that external commands used
# are available across platforms (Ubuntu minimal, macOS, Windows Git Bash)
#
# Usage: check-commands.sh

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

# Commands that are NOT reliably available in minimal CI environments
# Format: command|alternative
DISALLOWED=(
    "bc|awk 'BEGIN {printf \"%.2f\", x/y}'"
    "dc|awk for calculations"
    "seq|bash: for ((i=1; i<=n; i++)) or awk"
    "timeout|not on macOS - use background + sleep + kill pattern"
    "readarray|bash 4+ only - use while read loop"
    "mapfile|bash 4+ only - use while read loop"
    "column|not in minimal images - use printf with fixed widths"
    "numfmt|GNU only - use awk"
    "shuf|GNU only - use sort -R or awk"
    "tac|GNU only - use tail -r (BSD) or awk"
)

main() {
    cd "$ROOT_DIR"

    log_info "Checking shell scripts for CI-incompatible commands..."

    local total_errors=0

    # Build grep pattern from disallowed commands
    local pattern=""
    for entry in "${DISALLOWED[@]}"; do
        local cmd="${entry%%|*}"
        if [[ -n "$pattern" ]]; then
            pattern="$pattern|"
        fi
        # Match command at start of line, after pipe, or in $()
        pattern="$pattern\\b${cmd}\\b"
    done

    # Find all shell scripts and check them
    while IFS= read -r script; do
        # Search for disallowed commands (as actual commands, not variables)
        # Look for: command at line start, after |, after $( , after `
        local matches
        matches=$(grep -nE "(^[[:space:]]*|[|&;]\s*|\$\(|^[[:space:]]*if\s+)($pattern)" "$script" 2>/dev/null || true)

        if [[ -n "$matches" ]]; then
            while IFS= read -r match; do
                [[ -z "$match" ]] && continue

                local line_num="${match%%:*}"
                local line_content="${match#*:}"

                # Determine which command was matched
                for entry in "${DISALLOWED[@]}"; do
                    local cmd="${entry%%|*}"
                    local alt="${entry#*|}"

                    if echo "$line_content" | grep -qE "(^[[:space:]]*|[|&;]\s*|\$\()${cmd}\\b"; then
                        # Skip if it's a variable assignment like: local timeout=30
                        if echo "$line_content" | grep -qE "^\s*(local\s+|export\s+|readonly\s+)?${cmd}="; then
                            continue
                        fi
                        # Skip if it's in a comment
                        if echo "$line_content" | grep -qE "^\s*#"; then
                            continue
                        fi
                        # Skip YAML keys in heredocs (e.g., "timeout: 3s" in compose files)
                        # cmd followed by : is never a valid bash command invocation
                        if echo "$line_content" | grep -qE "\\b${cmd}:"; then
                            continue
                        fi

                        log_error "$script:$line_num: '$cmd' not available in minimal CI"
                        echo "  Line: $line_content"
                        echo "  Fix:  $alt"
                        echo ""
                        ((total_errors++))
                        break
                    fi
                done
            done <<<"$matches"
        fi
    done < <(
        find .ci -name "*.sh" -type f 2>/dev/null
        echo "./run.sh"
    )

    if [[ $total_errors -gt 0 ]]; then
        echo ""
        log_error "Found $total_errors CI-incompatible command(s)"
        log_info "These commands may not be available in ubuntu-slim or other minimal CI images"
        exit 1
    else
        log_success "All commands are CI-compatible"
    fi
}

main "$@"
