#!/bin/bash
# Security audit with allowlist support
# Used by both ./run.sh quality audit and CI
#
# Two-pass strategy:
#   1. Production deps (--omit=dev): hard fail, no allowlist permitted
#   2. All deps: allowlist applies only to dev-only vulnerabilities

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

# Run npm audit and validate output. Sets $audit_file to the output path.
# Usage: run_audit <output_file> [extra_flags...]
run_audit() {
    local output="$1"
    shift
    local audit_exit=0
    npm audit --json "$@" >"$output" || audit_exit=$?

    if ! jq empty "$output" 2>/dev/null; then
        log_error "npm audit failed to produce valid JSON (exit code: $audit_exit)"
        log_error "This may indicate a network error or npm registry issue"
        exit 1
    fi
}

# Extract unique advisory source IDs from an audit report
get_advisories() {
    jq -r '[.vulnerabilities[].via[] | select(type == "object") | .source] | unique | .[]' "$1" 2>/dev/null || echo ""
}

# Load allowlist IDs from .audit-allowlist (strip comments and blanks)
load_allowlist() {
    local ALLOWED=()
    if [[ -f ".audit-allowlist" ]]; then
        while IFS= read -r line; do
            line="${line%%#*}"
            line="${line// /}"
            [[ -n "$line" ]] && ALLOWED+=("$line")
        done <.audit-allowlist
    fi
    echo "${ALLOWED[@]}"
}

main() {
    cd "$ROOT_DIR"

    # ── Pass 1: Production dependencies (no allowlist) ──────────────
    log_info "Auditing production dependencies (no allowlist)"
    run_audit audit-prod.json --omit=dev

    local prod_total prod_high prod_critical
    prod_total=$(jq '.metadata.vulnerabilities.total // 0' audit-prod.json)
    prod_high=$(jq '.metadata.vulnerabilities.high // 0' audit-prod.json)
    prod_critical=$(jq '.metadata.vulnerabilities.critical // 0' audit-prod.json)

    if [[ "$prod_total" -gt 0 ]]; then
        ci_error "Production vulnerabilities: $prod_critical critical, $prod_high high, $prod_total total — cannot be allowlisted"
        log_info "See audit-prod.json for details"
        exit 1
    fi

    log_success "No production vulnerabilities"

    # ── Pass 2: All dependencies (allowlist applies to dev-only) ────
    log_info "Auditing all dependencies (allowlist for dev-only)"
    run_audit audit-report.json

    local all_total all_critical all_high
    all_total=$(jq '.metadata.vulnerabilities.total // 0' audit-report.json)
    all_critical=$(jq '.metadata.vulnerabilities.critical // 0' audit-report.json)
    all_high=$(jq '.metadata.vulnerabilities.high // 0' audit-report.json)

    # Advisories already covered by pass 1 (prod) — skip those, they passed
    local prod_advisories all_advisories
    prod_advisories=$(get_advisories audit-prod.json)
    all_advisories=$(get_advisories audit-report.json)

    # Dev-only advisories = all advisories minus prod advisories
    local dev_only_advisories=""
    for advisory in $all_advisories; do
        local is_prod=false
        for pa in $prod_advisories; do
            [[ "$advisory" == "$pa" ]] && is_prod=true && break
        done
        [[ "$is_prod" == "false" ]] && dev_only_advisories="$dev_only_advisories $advisory"
    done

    # Check dev-only advisories against allowlist
    local allowed_list
    read -ra ALLOWED_ADVISORIES <<<"$(load_allowlist)"

    local unallowed=""
    for advisory in $dev_only_advisories; do
        local found=false
        for allowed in "${ALLOWED_ADVISORIES[@]}"; do
            [[ "$advisory" == "$allowed" ]] && found=true && break
        done
        [[ "$found" == "false" ]] && unallowed="$unallowed $advisory"
    done

    if [[ -n "$unallowed" ]]; then
        ci_error "New dev vulnerabilities found: $all_critical critical, $all_high high"
        log_info "Unallowed advisories:$unallowed"
        log_info "See audit-report.json for details"
        log_info "If unfixable, add advisory ID to .audit-allowlist"
        exit 1
    fi

    local dev_only_count
    dev_only_count=$(echo "$dev_only_advisories" | wc -w)
    if [[ "$dev_only_count" -gt 0 ]]; then
        ci_warn "Allowed dev vulnerabilities: $dev_only_count (see .audit-allowlist)"
    fi

    log_success "Security audit passed"
    rm -f audit-report.json audit-prod.json
}

main "$@"
