#!/bin/bash
# Security audit with allowlist support
# Used by both ./go quality audit and CI

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Colors (disabled in CI)
if [[ "${CI:-}" == "true" ]]; then
    RED="" GREEN="" YELLOW="" NC=""
else
    RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[1;33m' NC='\033[0m'
fi

log_error() { echo -e "${RED}✗ $1${NC}" >&2; }
log_success() { echo -e "${GREEN}✓ $1${NC}"; }
log_warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
log_info() { echo -e "→ $1"; }

# GitHub Actions annotations
ci_error() { [[ "${CI:-}" == "true" ]] && echo "::error::$1" || log_error "$1"; }
ci_warn() { [[ "${CI:-}" == "true" ]] && echo "::warning::$1" || log_warn "$1"; }

main() {
    cd "$ROOT_DIR"

    log_info "Running security audit"

    npm audit --json > audit-report.json || true

    # Load allowlist from shared config (strip comments and empty lines)
    local ALLOWED_ADVISORIES=()
    if [[ -f ".audit-allowlist" ]]; then
        while IFS= read -r line; do
            line="${line%%#*}"  # Remove comments
            line="${line// /}"  # Remove spaces
            [[ -n "$line" ]] && ALLOWED_ADVISORIES+=("$line")
        done < .audit-allowlist
    fi

    # Get all unique advisory IDs from vulnerabilities
    local advisories
    advisories=$(jq -r '[.vulnerabilities[].via[] | select(type == "object") | .source] | unique | .[]' audit-report.json 2>/dev/null || echo "")

    # Check for any advisory not in allowlist
    local unallowed=""
    for advisory in $advisories; do
        local found=false
        for allowed in "${ALLOWED_ADVISORIES[@]}"; do
            [[ "$advisory" == "$allowed" ]] && found=true && break
        done
        [[ "$found" == "false" ]] && unallowed="$unallowed $advisory"
    done

    local total critical high
    total=$(jq '.metadata.vulnerabilities.total // 0' audit-report.json 2>/dev/null || echo "0")
    critical=$(jq '.metadata.vulnerabilities.critical // 0' audit-report.json 2>/dev/null || echo "0")
    high=$(jq '.metadata.vulnerabilities.high // 0' audit-report.json 2>/dev/null || echo "0")

    if [[ -n "$unallowed" ]]; then
        ci_error "New vulnerabilities found: $critical critical, $high high"
        log_info "Unallowed advisories:$unallowed"
        log_info "See audit-report.json for details"
        log_info "If unfixable, add advisory ID to .audit-allowlist"
        exit 1
    fi

    if [[ "$total" -gt 0 ]]; then
        ci_warn "Allowed vulnerabilities: $total (see .audit-allowlist)"
    fi

    log_success "Security audit passed"
    rm -f audit-report.json
}

main "$@"
