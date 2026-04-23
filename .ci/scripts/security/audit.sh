#!/bin/bash
# Security audit with allowlist support + AI-navigable GHSA URLs.
# Used by both ./run.sh quality audit and CI.
#
# Strict gate: an allowlisted advisory with an available fix (any form —
# transitive, non-breaking upgrade, or major upgrade) FAILS CI unless its
# allowlist entry carries an explicit "# BLOCKER: <reason>" comment line
# immediately above the numeric ID. BLOCKER comments are the single escape
# hatch and must document why we cannot take the fix right now.
#
# Every emitted error/warning carries the advisory's GitHub Advisory URL
# (https://github.com/advisories/GHSA-…), severity, and title so that AI
# agents reviewing the CI output can navigate directly to the CVE data.
#
# Two-pass strategy:
#   1. Production deps (--omit=dev): hard fail, no allowlist permitted
#   2. All deps: allowlist applies only to dev-only vulnerabilities
#   3. Stale-entry sweep over the final allowlists (strict / BLOCKER-gated)

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

# Advisory metadata populated by build_advisory_map, keyed by source ID
declare -A ADV_URL ADV_TITLE ADV_SEVERITY ADV_GHSA
# Enriched fields populated from the GitHub Advisory Database (gh api /advisories/<ghsa>)
declare -A ADV_VULN_RANGE ADV_PATCHED_VERSION ADV_DESC_PREVIEW

# Per-run advisory detail cache (survives between pass 1/pass 3 on the same run).
# Never committed — see .gitignore.
ADVISORY_CACHE_DIR=".audit-advisory-cache"

# Allowlist maps populated by parse_allowlist
declare -A ALLOWED_PROD BLOCKER_PROD
declare -A ALLOWED_DEV BLOCKER_DEV

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

# Populate ADV_URL / ADV_TITLE / ADV_SEVERITY / ADV_GHSA from an audit JSON file,
# then enrich with ADV_VULN_RANGE / ADV_PATCHED_VERSION / ADV_DESC_PREVIEW by
# fetching each GHSA entry from the GitHub Advisory Database in parallel.
# Later calls overwrite earlier ones for the same advisory ID (harmless —
# these fields are stable across passes).
build_advisory_map() {
    local audit_json="$1"
    local source severity url title ghsa
    while IFS=$'\t' read -r source severity url title; do
        [[ -z "$source" ]] && continue
        ADV_URL[$source]="$url"
        ADV_TITLE[$source]="$title"
        ADV_SEVERITY[$source]="$severity"
        # Extract GHSA-xxxx-xxxx-xxxx from the URL (npm audit URLs always follow this shape)
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

# Fetch GHSA entries for every advisory in ADV_GHSA that we haven't cached yet.
# Writes <ADVISORY_CACHE_DIR>/<GHSA>.json, one per advisory. Runs up to 8 fetches
# in parallel. Fetch failures (no network, missing GHSA, gh unauthenticated) are
# swallowed: the cache file is written as "{}" so downstream code degrades
# gracefully to URL-less output.
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

    # Parallel fetch. Use gh CLI which picks up GITHUB_TOKEN in CI; falls back to
    # anonymous API (60 requests/hour) locally. Any error → empty cache entry.
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
# description_preview is truncated to ~240 chars to keep CI annotations compact.
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

# Parse an allowlist file into two associative arrays:
#   allowed_ref[$id] = 1  when $id appears as a bare numeric line
#   blocker_ref[$id] = <reason>  when a "# BLOCKER: <reason>" line appears
#                                in the contiguous comment block above $id
# A blank line resets the tracked BLOCKER, so a single BLOCKER comment can
# cover a grouped list of related IDs until the next blank line.
# Usage: parse_allowlist <file> <allowed_var> <blocker_var>
parse_allowlist() {
    local file="$1"
    local -n allowed_ref="$2"
    local -n blocker_ref="$3"
    local current_blocker=""
    local line stripped

    [[ ! -f "$file" ]] && return

    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip surrounding whitespace
        stripped="${line#"${line%%[![:space:]]*}"}"
        stripped="${stripped%"${stripped##*[![:space:]]}"}"

        if [[ -z "$stripped" ]]; then
            current_blocker=""
        elif [[ "$stripped" =~ ^#[[:space:]]*BLOCKER:[[:space:]]*(.+)$ ]]; then
            current_blocker="${BASH_REMATCH[1]}"
        elif [[ "$stripped" =~ ^# ]]; then
            : # plain comment — preserve current_blocker
        elif [[ "$stripped" =~ ^[0-9]+$ ]]; then
            allowed_ref[$stripped]=1
            blocker_ref[$stripped]="$current_blocker"
        fi
    done <"$file"
}

# Low-effort BLOCKER patterns (exact match after normalization).
# Mirrors .ci/scripts/quality/check-review-comments.sh's review-gate philosophy:
# an "ack-tier" reason like "no fix" or "tbd" cannot serve as an escape hatch.
# A good BLOCKER names the upstream pin, the package chain, OR why runtime is
# not affected — enough for a future reviewer (or AI) to verify the claim.
readonly LOW_EFFORT_BLOCKER_PATTERNS=(
    # npm-audit ack-tier phrases
    "no fix" "no fix available" "no fix yet" "no upstream fix" "no fix published"
    "no patch" "no patch yet" "no patch available"
    "none" "n/a" "na" "empty" "-"
    # scheduling ack-tier
    "tbd" "wip" "fixme" "todo" "later" "fix later" "will fix" "pending"
    "skip" "skipping" "skipped" "ignore" "ignoring" "ignored"
    "unknown" "unknown reason" "idk" "dunno" "whatever"
    # review-gate-style ack phrases (copied from check-review-comments.sh)
    "ok" "okay" "ack" "acknowledged" "noted" "done" "fixed" "applied"
    "addressed" "updated" "changed" "understood"
    # explicit escape-hatch attempts
    "escape" "escape hatch" "suppressed" "suppress" "bypass" "override"
    "upstream issue" "transitive" "dev dep" "dev only"
)

# Minimum normalized-reason length. Catches short-but-not-banned phrases like
# "upstream transitive; no fix" (~25 chars) that sidestep the exact-match list
# while saying nothing concrete. 30 chars is enough to force naming a package
# AND a reason; every existing BLOCKER in .audit-{prod-,}allowlist clears it.
readonly BLOCKER_MIN_LENGTH=30

# Validate BLOCKER content is substantive.
# Returns 0 if acceptable, 1 if insufficient (prints error with guidance).
# Usage: validate_blocker_quality <id> <reason> <file>
validate_blocker_quality() {
    local id="$1" reason="$2" file="$3"
    # Normalize: lowercase, trim, strip trailing punctuation
    local normalized
    normalized=$(echo "$reason" |
        tr '[:upper:]' '[:lower:]' |
        sed 's/^[[:space:]]*//;s/[[:space:]]*$//' |
        sed 's/[.!?,;:]*$//')

    # Exact-match against the low-effort list
    local pattern
    for pattern in "${LOW_EFFORT_BLOCKER_PATTERNS[@]}"; do
        if [[ "$normalized" == "$pattern" ]]; then
            ci_error "Allowlist $file: BLOCKER for entry $id is a low-effort placeholder (\"$reason\")"
            echo "  Rejected because: \"$normalized\" matches the banned-phrase list — this adds no information beyond 'we suppressed it'"
            echo "  Action: write a specific reason. Good BLOCKERs cite the upstream pin, the package chain, OR why runtime isn't affected."
            echo "  Example: 'electron-builder 26.x pins plist > xmldom 0.8.x; build-time only, requires major electron migration'"
            return 1
        fi
    done

    # Minimum length enforcement
    if ((${#normalized} < BLOCKER_MIN_LENGTH)); then
        ci_error "Allowlist $file: BLOCKER for entry $id is too short (${#normalized} chars, minimum $BLOCKER_MIN_LENGTH)"
        echo "  Current: \"$reason\""
        echo "  Action: a BLOCKER must explain WHO pins what, WHY the fix cannot be taken now, and ideally WHEN to revisit."
        echo "  Example: 'axios 1.15.0 pins follow-redirects <1.16.0; not runtime-exposed in CLI auth path; revisit when axios bumps'"
        return 1
    fi

    return 0
}

# Fail if any allowlisted ID lacks a BLOCKER reason OR if its BLOCKER reason
# is low-effort/too-short. Run before audit work so allowlist self-inconsistency
# is its own clear failure mode, ahead of any npm audit calls.
# Usage: verify_allowlist_blockers <file> <blocker_var>
verify_allowlist_blockers() {
    local file="$1"
    # shellcheck disable=SC2178  # nameref to an associative array (blocker_ref is used as map)
    local -n blocker_ref="$2"
    local id missing=0
    for id in "${!blocker_ref[@]}"; do
        if [[ -z "${blocker_ref[$id]}" ]]; then
            ci_error "Allowlist $file: entry $id is missing a '# BLOCKER: <reason>' comment above it"
            echo "  Action: add a line like '# BLOCKER: <who pins what / why we cannot take the fix>' immediately above $id in $file"
            missing=1
        elif ! validate_blocker_quality "$id" "${blocker_ref[$id]}" "$file"; then
            missing=1
        fi
    done
    return $missing
}

# Map fixAvailable shape to a human fix hint.
# Usage: describe_fix <fix_type> <is_major> <fix_version> <fix_value>
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

# Emit a multi-line advisory annotation. The ::error:: / ::warning:: prefix
# stays on line 1 so GitHub's annotation extractor groups continuation lines
# with it in the Actions UI.
# Usage: emit_advisory <error|warn> <id> <pkg> <fix_hint> [action_hint]
emit_advisory() {
    local level="$1" id="$2" pkg="$3" fix_hint="$4" action_hint="${5:-}"
    local sev="${ADV_SEVERITY[$id]:-unknown}"
    local ghsa="${ADV_GHSA[$id]:-}"
    local title="${ADV_TITLE[$id]:-unknown advisory}"
    local vuln_range="${ADV_VULN_RANGE[$id]:-}"
    local patched="${ADV_PATCHED_VERSION[$id]:-}"
    local desc="${ADV_DESC_PREVIEW[$id]:-}"

    local header="Advisory $id ($pkg, $sev"
    [[ -n "$ghsa" ]] && header="$header, $ghsa"
    header="$header): $title"
    "ci_$level" "$header"

    if [[ -n "$vuln_range" || -n "$patched" ]]; then
        local range_line="  Affected: ${vuln_range:-unknown}"
        [[ -n "$patched" ]] && range_line="$range_line  →  Patched in: $patched"
        echo "$range_line"
    fi
    [[ -n "$desc" ]] && echo "  Summary: $desc"
    [[ -n "$fix_hint" ]] && echo "  Fix: $fix_hint"
    [[ -n "$action_hint" ]] && echo "  Action: $action_hint"
    return 0
}

# Resolve an advisory ID to its (pkg, fixAvailable-shape) info from an audit JSON.
# Usage: get_advisory_fix_info <advisory_id> <audit_json>
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
# Usage: check_stale_entries <allowlist_file> <audit_json> <allowed_var> <blocker_var>
check_stale_entries() {
    local allowlist_file="$1"
    local audit_json="$2"
    # shellcheck disable=SC2178  # namerefs to associative arrays
    local -n allowed_ref="$3"
    # shellcheck disable=SC2178
    local -n blocker_ref="$4"
    local advisory info fix_type is_major fix_version fix_value pkg hint

    for advisory in "${!allowed_ref[@]}"; do
        info=$(get_advisory_fix_info "$advisory" "$audit_json")
        [[ -z "$info" || "$info" == "null" ]] && continue

        fix_type=$(echo "$info" | jq -r '.fixType')
        is_major=$(echo "$info" | jq -r '.isMajor // "null"')
        fix_version=$(echo "$info" | jq -r '.fixVersion // empty')
        fix_value=$(echo "$info" | jq -r '.fixValue // "null"')
        pkg=$(echo "$info" | jq -r '.pkg')

        # Skip when npm reports no fix available — suppression is legitimate
        if [[ "$fix_type" == "boolean" && "$fix_value" == "false" ]]; then
            continue
        fi

        hint=$(describe_fix "$fix_type" "$is_major" "$fix_version" "$fix_value")

        if [[ -n "${blocker_ref[$advisory]:-}" ]]; then
            emit_advisory warn "$advisory" "$pkg" "$hint — BLOCKED: ${blocker_ref[$advisory]}"
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
    # This is its own pass — a self-inconsistent allowlist is clearly surfaced
    # before we run any npm audit work.
    log_info "Parsing allowlists"
    parse_allowlist ".audit-prod-allowlist" ALLOWED_PROD BLOCKER_PROD
    parse_allowlist ".audit-allowlist" ALLOWED_DEV BLOCKER_DEV

    local blockers_ok=0
    verify_allowlist_blockers ".audit-prod-allowlist" BLOCKER_PROD || blockers_ok=1
    verify_allowlist_blockers ".audit-allowlist" BLOCKER_DEV || blockers_ok=1
    if [[ $blockers_ok -ne 0 ]]; then
        log_error "Allowlist entries must include '# BLOCKER: <reason>' — strict gate enforced"
        exit 1
    fi

    # ── Pass 1: Production dependencies (no allowlist permitted for unknown entries) ──
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

    # Dev-only advisories = advisories in "all" but not in "prod"
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
    # Allowlisted advisory + ANY available fix + no BLOCKER  →  FAIL.
    # Allowlisted advisory + ANY available fix + BLOCKER      →  warn (reminder).
    # Allowlisted advisory + no fix upstream                    →  silent.
    log_info "Checking allowlist entries against available fixes (strict, BLOCKER-gated)"

    local stale_actionable=false
    check_stale_entries ".audit-prod-allowlist" audit-prod.json ALLOWED_PROD BLOCKER_PROD
    check_stale_entries ".audit-allowlist" audit-report.json ALLOWED_DEV BLOCKER_DEV

    if [[ "$stale_actionable" == "true" ]]; then
        log_error "One or more allowlisted advisories have available fixes without BLOCKER annotations — see errors above"
        # Keep audit files for inspection (audit-report.json is also consumed by CI artifact upload)
        exit 1
    fi

    log_success "Security audit passed"
    # Keep audit-report.json for ci-quality.yml artifact upload; clean sidecar only.
    rm -f audit-prod.json
}

main "$@"
