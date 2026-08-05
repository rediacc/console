#!/bin/bash
# Behavioural gate for `drill_summary`'s verdict logic (scripts/drills/lib.sh).
#
# WHY THIS EXISTS. On 2026-08-05 a drill that ran ZERO assertions — because its
# environment dependency was absent and declared — printed:
#
#     0 assertions: 0 passed, 0 failed
#     drill transfer PASSED
#
# Exit code 0, the word PASSED, and nothing whatsoever proven. A dashboard, a
# grep for PASSED, or a reader who did not scroll up to the declaration cannot
# tell that from a real pass. That is the vacuous-green shape the drills exist
# to catch, reproduced by the drills' own reporting.
#
# The fix makes a zero-assertion run print SKIPPED while keeping exit 0 (a
# DECLARED skip is legitimate; it is the word that was wrong). This gate is what
# stops it regressing, because nothing else can see it: every existing check
# reads exit codes, and the exit code was already correct. The bug lived
# entirely in what the run CLAIMED.
#
# CONTROL-FIRST. Four verdicts, and the gate fails itself if the harness cannot
# be driven at all:
#   1. 0 assertions          -> SKIPPED, and the word PASSED must NOT appear
#   2. all assertions pass   -> PASSED   (the CONTROL: without it, a summary
#                               hard-wired to SKIPPED would satisfy 1)
#   3. an assertion fails    -> FAILED + non-zero exit
#   4. --selftest with no failure -> refuses, because a planted failure that
#                               goes unnoticed means the accounting is broken
#
# Usage: check-drill-verdicts.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

cd "$(get_repo_root)"

DRILL_LIB="scripts/drills/lib.sh"

log_step "Checking drill verdict logic in $DRILL_LIB..."

if [[ ! -f "$DRILL_LIB" ]]; then
    log_error "$DRILL_LIB not found — this gate has nothing to check, which is a"
    log_error "failure, not a pass: a harness that vanished cannot be verified."
    exit 1
fi

# Drive drill_summary in a subshell with the counters set directly. `set +eu` for
# the same reason the probe gate needs it: these libraries are not written to be
# sourced under strict flags, and a half-loaded library would leave the function
# undefined — which would make every assertion below pass VACUOUSLY, i.e. exactly
# the defect this gate exists to catch, committed by the gate itself.
#
# Returns "<exit-code>|<stdout>" so callers can assert on BOTH. Asserting only on
# the exit code is what let the original defect through.
run_summary() {
    local count="$1" failures="$2" selftest="${3:-0}"
    (
        set +eu
        # shellcheck disable=SC1090
        source "$DRILL_LIB" >/dev/null 2>&1
        declare -F drill_summary >/dev/null || exit 97
        DRILL_NAME="gatecheck"
        DRILL_STARTED_AT=$(date +%s)
        DRILL_COUNT="$count"
        DRILL_FAILURES="$failures"
        DRILL_SELFTEST="$selftest"
        DRILL_ROWS=()
        out="$(drill_summary 2>&1)"
        rc=$?
        printf '%s|%s' "$rc" "$out"
    )
}

# Prove the harness is reachable before trusting a single verdict.
probe="$(run_summary 1 0 || true)"
if [[ "${probe%%|*}" == "97" ]]; then
    log_error "Could not load drill_summary from $DRILL_LIB."
    log_error "Refusing to report on a harness this gate cannot actually drive."
    exit 1
fi

failures=0

assert_verdict() {
    local label="$1" count="$2" fails="$3" selftest="$4" want_rc="$5" want_word="$6" forbid_word="$7"
    local result rc out
    result="$(run_summary "$count" "$fails" "$selftest" || true)"
    # An empty capture means the subshell died before its printf, i.e. the harness
    # could not be driven at all. Say that, rather than letting it fall through to
    # the rc comparison below and surface as the cryptic "expected exit 0, got ".
    # A gate whose probe failed must not be able to look like a gate whose probe
    # returned nothing interesting.
    if [[ -z "$result" ]]; then
        log_error "$label: run_summary produced no output — drill_summary could not be driven."
        failures=$((failures + 1))
        return
    fi
    rc="${result%%|*}"
    out="${result#*|}"

    if [[ "$rc" != "$want_rc" ]]; then
        log_error "$label: expected exit $want_rc, got $rc"
        failures=$((failures + 1))
        return
    fi
    if ! grep -q "$want_word" <<<"$out"; then
        log_error "$label: verdict '$want_word' missing from the summary."
        log_error "  got: $(tr '\n' ' ' <<<"$out" | tail -c 200)"
        failures=$((failures + 1))
        return
    fi
    if [[ -n "$forbid_word" ]] && grep -q "$forbid_word" <<<"$out"; then
        log_error "$label: the summary says '$forbid_word', which a dashboard or a"
        log_error "  grep will read as proof. A run that asserted nothing must not"
        log_error "  claim it passed — that is the 2026-08-05 defect."
        failures=$((failures + 1))
        return
    fi
    log_info "$label"
}

# 1. THE DEFECT: nothing asserted must not claim a pass (exit 0 is correct).
assert_verdict "0 assertions reads as SKIPPED, never PASSED" 0 0 0 0 "SKIPPED" "PASSED"

# 2. THE CONTROL: a real pass must still say PASSED, or assertion 1 is meaningless.
assert_verdict "a passing run still reads as PASSED (control fired)" 3 0 0 0 "PASSED" ""

# 3. A failure must be loud and non-zero.
assert_verdict "a failing run reads as FAILED and exits non-zero" 3 1 0 1 "FAILED" ""

# 4. A selftest whose planted failure did not fire must refuse.
assert_verdict "selftest with no failure refuses (accounting broken)" 3 0 1 1 "SELFTEST DID NOT FIRE" ""

if [[ "$failures" -gt 0 ]]; then
    log_error "$failures drill-verdict check(s) failed"
    exit 1
fi

log_info "Drill verdicts behave correctly (skipped, passed, failed, and selftest controls all fired)"
