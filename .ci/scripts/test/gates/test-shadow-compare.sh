#!/bin/bash
# Drives the REAL shadow-compare body, extracted from .github/workflows/ci.yml,
# against fixture values. Not a copy of it: a copy would keep passing after the
# workflow changed, which is the failure mode this whole battery exists to stop.
#
# WHY THIS EXISTS. The compare step is the only thing standing between the
# migration and deleting an org secret whose Bitwarden twin holds a DIFFERENT
# VALUE. It is also, until the cutover, a step near the top of all 62 jobs in
# this repo -- so its exit code decides whether the rest of each job runs. On
# 2026-09-03 that cost the CI watchdog entirely: run 33704079162 reported
# "failure" having monitored nothing, because the compare exited 1 before the
# monitor step. The scaffold had switched off the guard for every other run.
#
# So the body now has an expected-mismatch ledger, and a ledger is exactly the
# kind of escape hatch that rots into a blanket exemption. Every one of the six
# paths below is asserted, in BOTH directions.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT

python3 - "$REPO_ROOT/.github/workflows/ci.yml" "$BODY" <<'PY'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
for j in (d.get("jobs") or {}).values():
    for s in (j.get("steps") or []):
        if s.get("name") == "Compare shadow secrets against GitHub":
            open(sys.argv[2], "w").write(s["run"])
            sys.exit(0)
sys.exit("no compare step found in ci.yml -- the extraction is stale, so every verdict below would be about nothing")
PY
[ -s "$BODY" ] || log_fail "extracted an EMPTY compare body; refusing to report on it"

run_body() { # run_body <names> <expected> [VAR=VAL...]
    local names="$1" expected="$2"
    shift 2
    local rc=0
    LAST_OUT=$(env -i PATH="$PATH" SHADOW_NAMES="$names" SHADOW_EXPECTED_MISMATCH="$expected" \
        "$@" bash "$BODY" 2>&1) || rc=$?
    return "$rc"
}

# ── 1. The ordinary pass ───────────────────────────────────────────────────
test_match_passes() {
    local rc=0
    run_body "A" "" GH_A=same BWS_A=same || rc=$?
    assert_exit_code 0 "$rc" "two equal values must pass"
    assert_contains "$LAST_OUT" "shadow A match" "and say so"
    log_pass "a matching pair passes"
}

# ── 2. THE PLANT: an unexcused mismatch is still fatal ─────────────────────
test_mismatch_fails() {
    local rc=0
    run_body "A" "" GH_A=one BWS_A=two || rc=$?
    assert_exit_code 1 "$rc" "an UNEXCUSED mismatch must still fail -- this is the whole gate"
    assert_contains "$LAST_OUT" "shadow A MISMATCH" "and name it"
    log_pass "an unexcused mismatch fails, so the ledger did not defang the check"
}

# ── 3. The ledger excuses a KNOWN mismatch, loudly ─────────────────────────
test_expected_mismatch_passes() {
    local rc=0
    run_body "A" "A" GH_A=one BWS_A=two || rc=$?
    assert_exit_code 0 "$rc" "a listed mismatch must not stop the job"
    assert_contains "$LAST_OUT" "EXPECTED" "and must still SAY it mismatched"
    assert_contains "$LAST_OUT" "shadow-expected-mismatches.json" "pointing at where the reason lives"
    log_pass "a recorded mismatch is reported without blocking"
}

# ── 4. LIVENESS: an excuse dies with the condition for it ──────────────────
test_expected_but_matching_fails() {
    local rc=0
    run_body "A" "A" GH_A=same BWS_A=same || rc=$?
    assert_exit_code 1 "$rc" "a listed name that MATCHES must fail until its entry is deleted"
    assert_contains "$LAST_OUT" "the drift is resolved" "and say which way it is wrong"
    log_pass "an exemption cannot outlive the drift that justified it"
}

# ── 5. An empty stays fatal even when excused ──────────────────────────────
# The ledger describes a known VALUE drift. An empty side is a broken fetch,
# and excusing it would let the shadow report on secrets it never read.
test_empty_still_fatal_when_expected() {
    local rc=0
    run_body "A" "A" GH_A=one BWS_A= || rc=$?
    assert_exit_code 1 "$rc" "an EMPTY side must stay fatal even for a listed name"
    assert_contains "$LAST_OUT" "nothing was compared" "and say nothing was compared"
    log_pass "the ledger excuses drift, never an unread secret"
}

# ── 6. An excuse that excuses nothing here is refused ──────────────────────
test_expected_not_in_names() {
    local rc=0
    run_body "A" "B" GH_A=same BWS_A=same || rc=$?
    assert_exit_code 1 "$rc" "a listed name this job never compares is refused"
    assert_contains "$LAST_OUT" "excuses nothing here" "and says so"
    log_pass "a stale entry cannot hide in a job that never compares it"
}

# ── 7. CONTROL: the excuse must be what changes the verdict ────────────────
# Cases 2 and 3 differ ONLY in SHADOW_EXPECTED_MISMATCH. If both passed or both
# failed, the ledger would not be the thing doing the work and cases 3-6 would
# be measuring something else.
test_control_ledger_is_the_variable() {
    local a=0 b=0
    run_body "A" "" GH_A=one BWS_A=two || a=$?
    run_body "A" "A" GH_A=one BWS_A=two || b=$?
    [ "$a" -eq 1 ] && [ "$b" -eq 0 ] ||
        log_fail "CONTROL: identical inputs gave rc=$a and rc=$b; the ledger is not the deciding variable"
    log_pass "CONTROL: the ledger, and nothing else, flips the verdict"
}

log_test "test-shadow-compare"
test_match_passes
test_mismatch_fails
test_expected_mismatch_passes
test_expected_but_matching_fails
test_empty_still_fatal_when_expected
test_expected_not_in_names
test_control_ledger_is_the_variable

echo ""
log_pass "all tests passed"
