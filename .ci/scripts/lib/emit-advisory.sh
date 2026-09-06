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
#
# DEFERENCE RULE (added 2026-09-06 after a real defect): every assignment and
# every function definition below is conditional. This library is sourced both
# standalone AND, transitively, after common.sh has already installed its own
# logger, and in the second case common.sh must win.
#
# The defect: four quality gates -- check-profiler-coverage.sh,
# check-swallowed-failures.sh, check-ci-job-aggregation.sh and
# check-go-deps.sh -- source common.sh, then blocker-validator.sh, which
# sources this file at blocker-validator.sh:26. The old unconditional
# assignments clobbered common.sh's TTY-gated logger, with two consequences:
#   1. log_info / log_warn / log_success flipped from stderr (common.sh) to
#      stdout (here), so colour escapes leaked into anything that piped a
#      gate's stdout for data.
#   2. log_error interpolated "$1", so `log_error a b` silently dropped "b"
#      while common.sh's "$*" would have kept it. Every log_* below now uses
#      "$*" for the same reason, standalone callers included.
# check-pool-writer-safety.sh sources only common.sh, never reaches
# blocker-validator.sh, and so was never affected by any of this.
#
# WHY set-vs-unset, and not `${RED-}`: common.sh DELIBERATELY sets RED='' (and
# the rest) when stderr is not a tty. An emptiness test would read that
# deliberate empty string as "nobody assigned this" and paint the escapes back
# in, reintroducing the exact bug. `${RED+x}` is empty only when RED was never
# assigned at all, which is the question actually being asked.
#
# WHY `if ... fi` rather than `[[ ... ]] && VAR=...`: the last statement in a
# sourced branch supplies the source's exit status, and every caller here runs
# under common.sh's `set -euo pipefail`. A short-circuited `&&` would return 1
# and abort the sourcing script the moment a variable was already set.
if [[ "${CI:-}" == "true" ]]; then
    if [[ -z ${RED+x} ]]; then RED=""; fi
    if [[ -z ${GREEN+x} ]]; then GREEN=""; fi
    if [[ -z ${YELLOW+x} ]]; then YELLOW=""; fi
    if [[ -z ${NC+x} ]]; then NC=""; fi
else
    if [[ -z ${RED+x} ]]; then RED='\033[0;31m'; fi
    if [[ -z ${GREEN+x} ]]; then GREEN='\033[0;32m'; fi
    if [[ -z ${YELLOW+x} ]]; then YELLOW='\033[1;33m'; fi
    if [[ -z ${NC+x} ]]; then NC='\033[0m'; fi
fi

# `declare -F <name>` succeeds only when a function of that name is already in
# scope, so a real definition sourced earlier (common.sh's) is left untouched.
# common.sh defines log_info / log_warn / log_error but NOT log_success, so in
# the transitive case the definition below is the one that supplies it -- which
# is why it still has to respect the colours common.sh emptied above.
if ! declare -F log_error >/dev/null; then
    log_error() { echo -e "${RED}✗ $*${NC}" >&2; }
fi
if ! declare -F log_success >/dev/null; then
    log_success() { echo -e "${GREEN}✓ $*${NC}"; }
fi
if ! declare -F log_warn >/dev/null; then
    log_warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
fi
if ! declare -F log_info >/dev/null; then
    log_info() { echo -e "→ $*"; }
fi

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
