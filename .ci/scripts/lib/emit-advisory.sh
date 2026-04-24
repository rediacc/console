#!/bin/bash
# Shared AI-navigable error/warning emission library.
#
# Source this file to get:
#   - ci_error / ci_warn that emit GitHub Actions annotations in CI
#   - log_error / log_warn / log_success / log_info with repo-standard colours
#   - emit_advisory for structured multi-line error messages
#
# Every quality-gate script should produce errors of a shape that lets an AI
# agent (or human reviewer) act without opening another tool:
#   - line 1 is the ::error:: / ::warning:: annotation header (pkg, severity, GHSA-style id)
#   - optional "  Affected:", "  Summary:", "  Fix:", "  Action:", "  Details:" lines
#
# Sibling convention: .ci/scripts/quality/check-review-comments.sh enforces
# the same "substantive output" philosophy on the PR side — see its
# LOW_EFFORT_PATTERNS list for the reply-side analog.

# Guard against double-sourcing.
[[ -n "${__EMIT_ADVISORY_SH_SOURCED:-}" ]] && return 0
readonly __EMIT_ADVISORY_SH_SOURCED=1

# Colours — disabled in CI so GitHub's log viewer doesn't show escape sequences.
if [[ "${CI:-}" == "true" ]]; then
    RED="" GREEN="" YELLOW="" NC=""
else
    RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[1;33m' NC='\033[0m'
fi

log_error() { echo -e "${RED}✗ $1${NC}" >&2; }
log_success() { echo -e "${GREEN}✓ $1${NC}"; }
log_warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
log_info() { echo -e "→ $1"; }

# GitHub Actions annotation emitters. Only the first line is a proper annotation;
# continuation lines (echoed by emit_advisory) appear in the step log grouped
# under the expandable step.
ci_error() { [[ "${CI:-}" == "true" ]] && echo "::error::$1" || log_error "$1"; }
ci_warn() { [[ "${CI:-}" == "true" ]] && echo "::warning::$1" || log_warn "$1"; }

# Declare the optional metadata arrays so emit_advisory's defaulted reads are
# safe under `set -u` even when the caller hasn't populated any entries.
# Re-declaring a pre-existing array preserves its contents.
declare -A ADV_URL ADV_TITLE ADV_SEVERITY ADV_GHSA 2>/dev/null || true
declare -A ADV_VULN_RANGE ADV_PATCHED_VERSION ADV_DESC_PREVIEW 2>/dev/null || true

# emit_advisory <level> <id> <name> <fix_hint> [action_hint]
#
# Level: error | warn
# id:    the identifier the caller wants to display (numeric advisory source,
#        package name, rule id, etc.)
# name:  human-readable subject (e.g., package name + severity + title)
# fix_hint:    optional; prefixed with "  Fix:"
# action_hint: optional; prefixed with "  Action:"
#
# Before calling, the caller may populate optional associative arrays with
# the advisory id as key to get additional inline context. Unset entries are
# skipped; none are required.
#   ADV_SEVERITY[$id]  — "critical"|"high"|"moderate"|"low"
#   ADV_TITLE[$id]     — short title
#   ADV_GHSA[$id]      — GHSA identifier (for security uses)
#   ADV_URL[$id]       — advisory URL (only emitted if non-empty)
#   ADV_VULN_RANGE[$id]     — "<= 1.15.11"
#   ADV_PATCHED_VERSION[$id] — "1.16.0"
#   ADV_DESC_PREVIEW[$id]    — short description (already truncated by caller)
#
# Always returns 0 so `set -e` callers don't trip on the trailing conditional.
emit_advisory() {
    local level="$1" id="$2" name="$3" fix_hint="$4" action_hint="${5:-}"
    local sev="${ADV_SEVERITY[$id]:-}"
    local ghsa="${ADV_GHSA[$id]:-}"
    local title="${ADV_TITLE[$id]:-}"
    local url="${ADV_URL[$id]:-}"
    local vuln_range="${ADV_VULN_RANGE[$id]:-}"
    local patched="${ADV_PATCHED_VERSION[$id]:-}"
    local desc="${ADV_DESC_PREVIEW[$id]:-}"

    # Compose header — include whatever metadata is available.
    local header="$id"
    local parens=""
    [[ -n "$name" ]] && parens="$name"
    [[ -n "$sev" ]] && parens="${parens:+$parens, }$sev"
    [[ -n "$ghsa" ]] && parens="${parens:+$parens, }$ghsa"
    [[ -n "$parens" ]] && header="$header ($parens)"
    [[ -n "$title" ]] && header="$header: $title"

    "ci_$level" "$header"

    if [[ -n "$vuln_range" || -n "$patched" ]]; then
        local range_line="  Affected: ${vuln_range:-unknown}"
        [[ -n "$patched" ]] && range_line="$range_line  →  Patched in: $patched"
        echo "$range_line"
    fi
    [[ -n "$desc" ]] && echo "  Summary: $desc"
    [[ -n "$fix_hint" ]] && echo "  Fix: $fix_hint"
    [[ -n "$action_hint" ]] && echo "  Action: $action_hint"
    [[ -n "$url" ]] && echo "  Details: $url"
    return 0
}
