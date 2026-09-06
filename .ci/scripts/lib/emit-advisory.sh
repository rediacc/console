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

# BASH 4.0 IS A HARD PRECONDITION OF THIS FILE, AND macOS SHIPS 3.2.57.
#
# `/bin/bash` on macOS is 3.2.57 -- Apple froze it at the last GPLv2 release --
# and every `.ci` library documents itself as locally runnable, so the platform
# is not ours to assume. That is the same argument `sed_in_place` already makes
# at common.sh:77, reached here from the other direction.
#
# WHAT BREAKS, DRIVEN ON A REAL bash 3.2.0 ON 2026-09-06 rather than reasoned
# about. The ADV_* tables below are ASSOCIATIVE arrays and `declare -A` does not
# exist before bash 4.0. The line that declared them read
# `declare -A ADV_URL ... 2>/dev/null || true`, which SWALLOWED the refusal, so
# the names stayed INDEXED arrays and every subscript was then evaluated as
# ARITHMETIC:
#
#   a numeric id ("1234")   lands at index 1234 and looks like it works
#   a package-name id       `ADV_SEVERITY[lodash]=critical` aborts the caller
#                           with "lodash: unbound variable" under `set -u`
#
# and the second case EXITS ZERO. Measured, script file, bash 3.2.0, streams read
# separately: stdout empty, stderr "line 3: lodash: unbound variable", exit 0.
# The identical script on bash 5.3.9 prints both advisories and exits 0. So a
# security gate that calls emit_advisory with a package-name id reports PASS on
# macOS having emitted nothing at all. That is the green-without-running shape,
# manufactured by the `2>/dev/null || true` that was there to keep the file
# quiet. `.ci/scripts/lib/age-check.sh:117` and
# `.ci/scripts/security/audit.sh:313-500` are the live callers.
#
# WHY A REFUSAL AND NOT A REWRITE. There is no bash 3.2 spelling of an
# associative array. Emulating one means re-keying every ADV_* into flat variable
# names and changing the public interface `audit.sh:82-83` writes to, in a file
# whose port is already recorded against a shadow ledger. A loud refusal naming
# the fix is the smaller and the honest change: it converts a silent wrong answer
# into one message. It does NOT make this file work on bash 3.2, and it is not
# pretending to.
#
# THREE SIBLING FILES carry the same precondition for their own reasons, and each
# states its own measured consequence rather than pointing here:
# blocker-validator.sh, release-age.sh, release-state-validator.sh. The count is
# written down for the same reason `_toolchain_sha256sum` writes down its own
# (toolchain.sh:267): it is the number that tells the next reader whether the
# pattern is shrinking.
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
    echo "emit-advisory.sh needs bash 4.0 or newer; this is bash ${BASH_VERSION:-unknown}." >&2
    echo "  Associative arrays (ADV_SEVERITY, ADV_TITLE, ...) do not exist before 4.0. On 3.2 a" >&2
    echo "  non-numeric advisory id aborts the caller with 'unbound variable' AND exits 0, so the" >&2
    echo "  gate reports PASS having emitted nothing." >&2
    echo "  Fix: brew install bash, put it first on PATH, and re-run; or run the gate in the devbox." >&2
    return 1
fi

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
#
# THE `2>/dev/null || true` THAT USED TO END BOTH LINES IS GONE, and its removal
# is the point of the version guard above rather than a tidy-up. It was there to
# excuse ONE failure, `declare: -A: invalid option` on bash 3.2, and in excusing
# it silently it produced the exit-0-with-nothing case argued at the top of this
# file. With 4.0 guaranteed the only remaining way `declare -A` can fail is a
# caller that already created one of these names as an INDEXED array, which is a
# real defect in that caller and must not be swallowed either: bash refuses with
# "cannot convert indexed to associative array" and every later `ADV_*[$id]`
# would then be arithmetic again, which is the same wrong answer by another road.
# So a failure is named and refused here, where the reader is holding the cause.
declare -A ADV_URL ADV_TITLE ADV_SEVERITY ADV_GHSA || {
    echo "emit-advisory.sh: cannot declare the ADV_* associative arrays (bash ${BASH_VERSION:-unknown})." >&2
    echo "  A caller has already created one of them as an indexed array. Remove that assignment;" >&2
    echo "  leaving it turns every ADV_*[\$id] subscript back into arithmetic." >&2
    return 1
}
declare -A ADV_VULN_RANGE ADV_PATCHED_VERSION ADV_DESC_PREVIEW || {
    echo "emit-advisory.sh: cannot declare the ADV_* associative arrays (bash ${BASH_VERSION:-unknown})." >&2
    echo "  A caller has already created one of them as an indexed array. Remove that assignment;" >&2
    echo "  leaving it turns every ADV_*[\$id] subscript back into arithmetic." >&2
    return 1
}

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
