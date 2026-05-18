#!/bin/bash
# Security audit with allowlist support + AI-navigable GHSA URLs.
# Used by both ./run.sh quality audit and CI.
#
# Strict gate: an allowlisted advisory with an available fix (any form —
# transitive, non-breaking upgrade, or major upgrade) FAILS CI unless its
# allowlist entry carries an explicit "# BLOCKER: <reason>" comment line
# that passes the shared blocker-validator quality gate.
#
# Every emitted error/warning carries the advisory's GitHub Advisory URL,
# severity, and title so AI agents reviewing CI output can act without
# opening a second tool.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# shellcheck source=../lib/emit-advisory.sh
# BLOCKER: standard CI error/warn helpers and emit_advisory shared across all quality scripts
source "$SCRIPT_DIR/../lib/emit-advisory.sh"
# shellcheck source=../lib/blocker-validator.sh
# BLOCKER: shared BLOCKER parser + quality validator used by every suppression gate
source "$SCRIPT_DIR/../lib/blocker-validator.sh"
# shellcheck source=../lib/age-check.sh
# BLOCKER: age-based rot detection for allowlist entries; warns at 180 days, fails at 365
source "$SCRIPT_DIR/../lib/age-check.sh"

# Advisory metadata populated by build_advisory_map, keyed by source ID
declare -A ADV_URL ADV_TITLE ADV_SEVERITY ADV_GHSA
# Enriched fields populated from the GitHub Advisory Database
declare -A ADV_VULN_RANGE ADV_PATCHED_VERSION ADV_DESC_PREVIEW

# Per-run advisory detail cache (survives between pass 1/pass 3 on the same run).
ADVISORY_CACHE_DIR=".audit-advisory-cache"

# Allowlist maps populated by parse_blockered_list
declare -A ALLOWED_PROD BLOCKER_PROD
declare -A ALLOWED_DEV BLOCKER_DEV

# Run npm audit and validate JSON output.
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

# Extract unique advisory source IDs from an audit report.
get_advisories() {
    jq -r '[.vulnerabilities[].via[] | select(type == "object") | .source] | unique | .[]' "$1" 2>/dev/null || echo ""
}

# Populate ADV_URL / ADV_TITLE / ADV_SEVERITY / ADV_GHSA from audit JSON,
# then enrich with ADV_VULN_RANGE / ADV_PATCHED_VERSION / ADV_DESC_PREVIEW
# by fetching each GHSA entry from the GitHub Advisory Database in parallel.
build_advisory_map() {
    local audit_json="$1"
    local source severity url title
    while IFS=$'\t' read -r source severity url title; do
        [[ -z "$source" ]] && continue
        ADV_URL[$source]="$url"
        ADV_TITLE[$source]="$title"
        ADV_SEVERITY[$source]="$severity"
        if [[ "$url" =~ (GHSA-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+) ]]; then
            ADV_GHSA[$source]="${BASH_REMATCH[1]}"
        else
            ADV_GHSA[$source]=""
        fi
    done < <(jq -r '[.vulnerabilities | to_entries[].value.via[]
                     | select(type == "object")
                     | {source, url, title, severity}]
                    | unique_by(.source)
                    | .[] | [.source, .severity, .url, .title] | @tsv' "$audit_json")

    fetch_advisory_details_parallel
}

# Fetch GHSA entries for every advisory we haven't cached yet. Runs up to 8
# fetches in parallel. Fetch failures are swallowed (empty cache file), so
# downstream code degrades gracefully to URL-less output.
fetch_advisory_details_parallel() {
    mkdir -p "$ADVISORY_CACHE_DIR"
    local ghsa ghsa_list=()
    for ghsa in "${ADV_GHSA[@]}"; do
        [[ -z "$ghsa" ]] && continue
        [[ -f "$ADVISORY_CACHE_DIR/$ghsa.json" ]] && continue
        ghsa_list+=("$ghsa")
    done
    ((${#ghsa_list[@]} == 0)) && {
        load_advisory_details
        return
    }

    printf '%s\n' "${ghsa_list[@]}" | xargs -P 8 -I {} bash -c '
        ghsa="$1"
        out="'"$ADVISORY_CACHE_DIR"'/$ghsa.json"
        if ! gh api "/advisories/$ghsa" > "$out" 2>/dev/null; then
            echo "{}" > "$out"
        fi
    ' _ {}

    load_advisory_details
}

# Populate ADV_VULN_RANGE / ADV_PATCHED_VERSION / ADV_DESC_PREVIEW from cached JSON.
load_advisory_details() {
    local source ghsa cache details
    for source in "${!ADV_GHSA[@]}"; do
        ghsa="${ADV_GHSA[$source]}"
        [[ -z "$ghsa" ]] && continue
        cache="$ADVISORY_CACHE_DIR/$ghsa.json"
        [[ ! -f "$cache" ]] && continue
        details=$(jq -r '
            [
                (.vulnerabilities[0].vulnerable_version_range // ""),
                (.vulnerabilities[0].first_patched_version // ""),
                ((.description // "") | gsub("\r"; "") | gsub("\n+"; " ") | gsub("\\*\\*|##|`"; "") | .[0:240])
            ] | @tsv
        ' "$cache" 2>/dev/null)
        IFS=$'\t' read -r ADV_VULN_RANGE[$source] ADV_PATCHED_VERSION[$source] ADV_DESC_PREVIEW[$source] <<<"$details"
    done
}

# Map fixAvailable shape to a human fix hint.
describe_fix() {
    local fix_type="$1" is_major="$2" fix_version="$3" fix_value="$4"
    case "$fix_type" in
        "null")
            echo "no fix information in npm audit output"
            ;;
        "boolean")
            if [[ "$fix_value" == "true" ]]; then
                echo "transitive fix path exists (try 'npm update <pkg>' or add a root overrides entry)"
            else
                echo "no fix available upstream"
            fi
            ;;
        "object")
            if [[ "$is_major" == "true" ]]; then
                echo "major upgrade required${fix_version:+ (to $fix_version)}"
            else
                echo "non-breaking upgrade available${fix_version:+ (to $fix_version)}"
            fi
            ;;
        *)
            echo "unknown fix type: $fix_type"
            ;;
    esac
}

# Resolve an advisory ID to its (pkg, fixAvailable-shape) info from an audit JSON.
get_advisory_fix_info() {
    local advisory="$1" audit_json="$2"
    jq -c --arg id "$advisory" '
        .vulnerabilities | to_entries[] |
        select(.value.via[] | objects | select(.source == ($id | tonumber))) |
        {
            pkg: .key,
            fixType: (.value.fixAvailable | type),
            fixValue: (if (.value.fixAvailable | type) == "boolean"
                       then (.value.fixAvailable | tostring)
                       else null end),
            isMajor: (if (.value.fixAvailable | type) == "object"
                      then (.value.fixAvailable.isSemVerMajor | tostring)
                      else null end),
            fixVersion: (if (.value.fixAvailable | type) == "object"
                         then .value.fixAvailable.version
                         else null end)
        }
    ' "$audit_json" 2>/dev/null | head -1
}

# Check every allowlisted ID against the audit JSON and emit advisory-level
# messages. BLOCKER'd entries stay at warning; un-BLOCKER'd entries with any
# available fix FAIL.
check_stale_entries() {
    local allowlist_file="$1"
    local audit_json="$2"
    local -n _allowed_ref="$3"
    local -n _blocker_ref="$4"
    local advisory info fix_type is_major fix_version fix_value pkg hint

    for advisory in "${!_allowed_ref[@]}"; do
        info=$(get_advisory_fix_info "$advisory" "$audit_json")
        [[ -z "$info" || "$info" == "null" ]] && continue

        fix_type=$(echo "$info" | jq -r '.fixType')
        is_major=$(echo "$info" | jq -r '.isMajor // "null"')
        fix_version=$(echo "$info" | jq -r '.fixVersion // empty')
        fix_value=$(echo "$info" | jq -r '.fixValue // "null"')
        pkg=$(echo "$info" | jq -r '.pkg')

        if [[ "$fix_type" == "boolean" && "$fix_value" == "false" ]]; then
            continue
        fi

        hint=$(describe_fix "$fix_type" "$is_major" "$fix_version" "$fix_value")

        if [[ -n "${_blocker_ref[$advisory]:-}" ]]; then
            emit_advisory warn "$advisory" "$pkg" "$hint — BLOCKED: ${_blocker_ref[$advisory]}"
        else
            emit_advisory error "$advisory" "$pkg" "$hint" \
                "take the fix OR add '# BLOCKER: <reason>' above $advisory in $allowlist_file"
            stale_actionable=true
        fi
    done
}

main() {
    cd "$ROOT_DIR"

    # Parse allowlists and fail fast on any entry missing a BLOCKER annotation.
    log_info "Parsing allowlists"
    parse_blockered_list ".audit-prod-allowlist" ALLOWED_PROD BLOCKER_PROD
    parse_blockered_list ".audit-allowlist" ALLOWED_DEV BLOCKER_DEV

    local blockers_ok=0
    verify_all_blockers ".audit-prod-allowlist" BLOCKER_PROD || blockers_ok=1
    verify_all_blockers ".audit-allowlist" BLOCKER_DEV || blockers_ok=1
    if [[ $blockers_ok -ne 0 ]]; then
        log_error "Allowlist entries must include a quality '# BLOCKER: <reason>' — strict gate enforced"
        exit 1
    fi

    # Age-based rot check: warn on entries > 180 days, fail on > 365 days.
    # Forces a re-review cadence on long-lived suppressions.
    log_info "Checking allowlist entry ages"
    local age_fail=0 id
    for id in "${!ALLOWED_PROD[@]}"; do
        check_entry_age ".audit-prod-allowlist" "$id" "$id" "audit-prod-allowlist entry" || age_fail=1
    done
    for id in "${!ALLOWED_DEV[@]}"; do
        check_entry_age ".audit-allowlist" "$id" "$id" "audit-allowlist entry" || age_fail=1
    done
    if [[ $age_fail -ne 0 ]]; then
        log_error "Allowlist entries older than $AGE_FAIL_DAYS days must be re-reviewed — strict age gate enforced"
        exit 1
    fi

    # ── Pass 0: Package signature / provenance verification ────────
    # Verifies every installed package's registry signature against the public
    # signing key, and provenance attestations where present. Failures are not
    # allowlistable — a bad signature means the lockfile points at a tampered
    # tarball.
    log_info "Verifying package signatures and provenance"
    if ! npm audit signatures 2>&1; then
        log_error "npm audit signatures failed — at least one installed package has an invalid signature or missing provenance"
        log_error "This indicates registry tampering, a poisoned lockfile, or a downgrade attack — do NOT allowlist"
        exit 1
    fi

    # ── Pass 1: Production dependencies ────────────────────────────
    log_info "Auditing production dependencies (no allowlist for new advisories)"
    run_audit audit-prod.json --omit=dev
    build_advisory_map audit-prod.json

    local prod_total prod_high prod_critical
    prod_total=$(jq '.metadata.vulnerabilities.total // 0' audit-prod.json)
    prod_high=$(jq '.metadata.vulnerabilities.high // 0' audit-prod.json)
    prod_critical=$(jq '.metadata.vulnerabilities.critical // 0' audit-prod.json)

    if [[ "$prod_total" -gt 0 ]]; then
        local prod_advisories_list prod_unallowed=() advisory
        prod_advisories_list=$(get_advisories audit-prod.json)
        for advisory in $prod_advisories_list; do
            [[ -n "${ALLOWED_PROD[$advisory]:-}" ]] || prod_unallowed+=("$advisory")
        done

        if ((${#prod_unallowed[@]} > 0)); then
            ci_error "Production vulnerabilities: $prod_critical critical, $prod_high high, $prod_total total"
            local info pkg fix_type is_major fix_version fix_value hint
            for advisory in "${prod_unallowed[@]}"; do
                info=$(get_advisory_fix_info "$advisory" audit-prod.json)
                pkg=$(echo "$info" | jq -r '.pkg // "unknown"')
                fix_type=$(echo "$info" | jq -r '.fixType')
                is_major=$(echo "$info" | jq -r '.isMajor // "null"')
                fix_version=$(echo "$info" | jq -r '.fixVersion // empty')
                fix_value=$(echo "$info" | jq -r '.fixValue // "null"')
                hint=$(describe_fix "$fix_type" "$is_major" "$fix_version" "$fix_value")
                emit_advisory error "$advisory" "$pkg" "$hint" \
                    "fix by upgrading/overriding the affected package, OR add '# BLOCKER: <reason>' above $advisory in .audit-prod-allowlist"
            done
            exit 1
        fi
        ci_warn "Allowed production vulnerabilities: $prod_total (see .audit-prod-allowlist)"
    fi

    log_success "No production vulnerabilities"

    # ── Pass 2: All dependencies (allowlist applies to dev-only) ────
    log_info "Auditing all dependencies (allowlist for dev-only)"
    run_audit audit-report.json
    build_advisory_map audit-report.json

    local all_total all_critical all_high
    all_total=$(jq '.metadata.vulnerabilities.total // 0' audit-report.json)
    all_critical=$(jq '.metadata.vulnerabilities.critical // 0' audit-report.json)
    all_high=$(jq '.metadata.vulnerabilities.high // 0' audit-report.json)

    local prod_advisories all_advisories advisory dev_only_advisories=()
    prod_advisories=$(get_advisories audit-prod.json)
    all_advisories=$(get_advisories audit-report.json)
    for advisory in $all_advisories; do
        local is_prod=false pa
        for pa in $prod_advisories; do
            [[ "$advisory" == "$pa" ]] && is_prod=true && break
        done
        [[ "$is_prod" == "false" ]] && dev_only_advisories+=("$advisory")
    done

    local unallowed=()
    for advisory in "${dev_only_advisories[@]+"${dev_only_advisories[@]}"}"; do
        [[ -n "${ALLOWED_DEV[$advisory]:-}" ]] || unallowed+=("$advisory")
    done

    if ((${#unallowed[@]} > 0)); then
        ci_error "New dev vulnerabilities: $all_critical critical, $all_high high"
        local info pkg fix_type is_major fix_version fix_value hint
        for advisory in "${unallowed[@]}"; do
            info=$(get_advisory_fix_info "$advisory" audit-report.json)
            pkg=$(echo "$info" | jq -r '.pkg // "unknown"')
            fix_type=$(echo "$info" | jq -r '.fixType')
            is_major=$(echo "$info" | jq -r '.isMajor // "null"')
            fix_version=$(echo "$info" | jq -r '.fixVersion // empty')
            fix_value=$(echo "$info" | jq -r '.fixValue // "null"')
            hint=$(describe_fix "$fix_type" "$is_major" "$fix_version" "$fix_value")
            emit_advisory error "$advisory" "$pkg" "$hint" \
                "fix by upgrading/overriding the affected package, OR add '# BLOCKER: <reason>' above $advisory in .audit-allowlist"
        done
        exit 1
    fi

    local dev_only_count="${#dev_only_advisories[@]}"
    if [[ "$dev_only_count" -gt 0 ]]; then
        ci_warn "Allowed dev vulnerabilities: $dev_only_count (see .audit-allowlist)"
    fi

    # ── Pass 3: Strict stale-entry sweep ────────────────────────────
    log_info "Checking allowlist entries against available fixes (strict, BLOCKER-gated)"

    local stale_actionable=false
    check_stale_entries ".audit-prod-allowlist" audit-prod.json ALLOWED_PROD BLOCKER_PROD
    check_stale_entries ".audit-allowlist" audit-report.json ALLOWED_DEV BLOCKER_DEV

    if [[ "$stale_actionable" == "true" ]]; then
        log_error "One or more allowlisted advisories have available fixes without BLOCKER annotations — see errors above"
        exit 1
    fi

    log_success "Security audit passed"
    # Keep audit-report.json for ci-quality.yml artifact upload; clean sidecar only.
    rm -f audit-prod.json
}

main "$@"
