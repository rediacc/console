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
        # Check if all production advisories are in .audit-prod-allowlist (upstream issues only)
        local prod_advisories_list
        prod_advisories_list=$(get_advisories audit-prod.json)
        local prod_allowed=()
        if [[ -f ".audit-prod-allowlist" ]]; then
            while IFS= read -r line; do
                line="${line%%#*}"
                line="${line// /}"
                [[ -n "$line" ]] && prod_allowed+=("$line")
            done <.audit-prod-allowlist
        fi
        local prod_unallowed=""
        for advisory in $prod_advisories_list; do
            local found=false
            for allowed in "${prod_allowed[@]+"${prod_allowed[@]}"}"; do
                [[ "$advisory" == "$allowed" ]] && found=true && break
            done
            [[ "$found" == "false" ]] && prod_unallowed="$prod_unallowed $advisory"
        done
        if [[ -n "$prod_unallowed" ]]; then
            ci_error "Production vulnerabilities: $prod_critical critical, $prod_high high, $prod_total total"
            log_info "Unallowed advisories:$prod_unallowed"
            log_info "See audit-prod.json for details"
            log_info "For upstream issues with no fix, add advisory ID to .audit-prod-allowlist"
            exit 1
        fi
        ci_warn "Allowed production vulnerabilities: $prod_total (see .audit-prod-allowlist)"
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

    # ── Pass 3: Check for stale allowlist entries ────────────────
    # When a suppressed vulnerability gets a fix upstream, flag it so
    # developers upgrade and remove the allowlist entry.
    # - Non-breaking fix (fixAvailable: true or isSemVerMajor: false): FAIL
    # - Major upgrade required (isSemVerMajor: true): WARN only
    log_info "Checking for stale allowlist entries (fixes now available)"

    local stale_actionable=false

    check_stale_entries() {
        local allowlist_file="$1"
        local audit_json="$2"
        local entries=()

        [[ ! -f "$allowlist_file" ]] && return

        while IFS= read -r line; do
            line="${line%%#*}"
            line="${line// /}"
            [[ -n "$line" ]] && entries+=("$line")
        done <"$allowlist_file"

        for advisory in "${entries[@]}"; do
            local fix_info
            fix_info=$(jq -c --arg id "$advisory" '
                .vulnerabilities | to_entries[] |
                select(.value.via[] | objects | select(.source == ($id | tonumber))) |
                {
                    pkg: .key,
                    fixType: (.value.fixAvailable | type),
                    isMajor: (if (.value.fixAvailable | type) == "object"
                              then .value.fixAvailable.isSemVerMajor
                              else null end),
                    fixVersion: (if (.value.fixAvailable | type) == "object"
                                 then .value.fixAvailable.version
                                 else null end)
                }
            ' "$audit_json" 2>/dev/null | head -1)

            [[ -z "$fix_info" || "$fix_info" == "null" ]] && continue

            local fix_type is_major fix_version pkg
            fix_type=$(echo "$fix_info" | jq -r '.fixType')
            is_major=$(echo "$fix_info" | jq -r '.isMajor // "null"')
            fix_version=$(echo "$fix_info" | jq -r '.fixVersion // empty')
            pkg=$(echo "$fix_info" | jq -r '.pkg')

            # fixAvailable forms:
            #   false          -> no fix, keep suppressed
            #   true (boolean) -> transitive fix path exists, warn only (may still require blocked upgrades)
            #   {isSemVerMajor: true}  -> fix via major upgrade, warn only
            #   {isSemVerMajor: false} -> non-breaking fix available, FAIL CI
            if [[ "$fix_type" == "object" && "$is_major" == "false" ]]; then
                ci_error "Advisory $advisory ($pkg) now has a non-breaking fix${fix_version:+ ($fix_version)} -- upgrade and remove from $allowlist_file"
                stale_actionable=true
            elif [[ "$fix_type" == "object" && "$is_major" == "true" ]]; then
                ci_warn "Advisory $advisory ($pkg) has a fix via major upgrade${fix_version:+ to $fix_version} -- review $allowlist_file"
            elif [[ "$fix_type" == "boolean" ]]; then
                ci_warn "Advisory $advisory ($pkg) may have a transitive fix available -- review $allowlist_file"
            fi
        done
    }

    check_stale_entries ".audit-prod-allowlist" "audit-prod.json"
    check_stale_entries ".audit-allowlist" "audit-report.json"

    if [[ "$stale_actionable" == "true" ]]; then
        log_error "Allowlisted advisories have non-breaking fixes available -- upgrade dependencies and remove stale entries"
        # Keep audit files for inspection
        exit 1
    fi

    log_success "Security audit passed"
    rm -f audit-report.json audit-prod.json
}

main "$@"
