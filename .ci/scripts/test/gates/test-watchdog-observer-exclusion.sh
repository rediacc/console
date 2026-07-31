#!/bin/bash
# The watchdog must never read an OBSERVER check as a failed CI job.
#
# WHY: minutes after "Review Complete" became a ruleset-required check
# (2026-07-31, run 30660765759), a push deadlocked: the not-yet-re-reviewed
# head's Review Complete check-run FAILED (correctly), it lands in the same
# github-actions check suite as the CI jobs, the watchdog's failure scan
# counted it and force-cancelled the run, and the re-review that would flip
# the check green only starts on a GREEN run. The fix is one config line
# (WATCHDOG_EXCLUDE_PATTERNS in watchdog-monitor.yml); this gate is what
# stops that line from quietly losing an entry and reintroducing the cycle.
#
# Control-first per the house rule: the checker is first proven to FIRE on a
# planted copy missing one exclusion, then run against the real workflow.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WORKFLOW="$REPO_ROOT/.github/workflows/watchdog-monitor.yml"
PASS=0

# exclusions_of <file>: the value of WATCHDOG_EXCLUDE_PATTERNS, or empty.
exclusions_of() {
    sed -n "s/.*WATCHDOG_EXCLUDE_PATTERNS: '\(.*\)'.*/\1/p" "$1" | head -1
}

# assert_excludes <file> <name>: 0 when <name> is a comma-separated member.
assert_excludes() {
    local val
    val="$(exclusions_of "$1")"
    [[ ",$val," == *",$2,"* ]]
}

# --- CONTROL: a copy missing 'Review Complete' must FAIL the assertion -----
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
sed "s/,Review Complete'/'/" "$WORKFLOW" >"$TMP/planted.yml"
if assert_excludes "$TMP/planted.yml" "Review Complete"; then
    log_fail "CONTROL failed: the checker passed a copy missing the exclusion"
    exit 1
fi
log_pass "CONTROL: the checker fires on a planted copy missing 'Review Complete'"
PASS=$((PASS + 1))

# The control must not have been vacuous: the planted copy still has a list.
[[ -n "$(exclusions_of "$TMP/planted.yml")" ]] || {
    log_fail "CONTROL is vacuous: the planted copy lost the whole env line"
    exit 1
}

# --- The real assertions ---------------------------------------------------
for name in "Watchdog" "CI Complete" "Review Complete"; do
    if assert_excludes "$WORKFLOW" "$name"; then
        log_pass "watchdog exclusion list carries '$name'"
        PASS=$((PASS + 1))
    else
        log_fail "WATCHDOG_EXCLUDE_PATTERNS lost '$name'; the observer-check deadlock (run 30660765759) returns without it"
        exit 1
    fi
done

log_pass "all $PASS assertion(s) passed"
