#!/bin/bash
# CI wrapper for the Stop-hook harness (.claude/hooks/stop/test-worklist-v5.sh).
#
# WHY THIS EXISTS. Its sibling test-claude-hooks.sh wraps the PRE-BASH/PRE-EDIT
# guard harness, and that asymmetry was invisible: the STOP hook — which gates
# the end of every turn, owns the worklist store, the deferral machinery and the
# judge subprocess — had a 431-case suite that ran only when somebody remembered
# to type it. A regression in it could never turn CI red.
#
# That gap was found the way these always are: a real Stop-gate defect shipped
# (the judge reported an empty stderr while the CLI wrote its error envelope to
# stdout, so the gate blocked with the unactionable "judge exited 1: "), and the
# test written to prevent its return had nowhere to run. A fix whose test cannot
# execute in CI is a fix with no gate.
#
# Modeled on test-claude-hooks.sh deliberately, down to the vacuity guard: a
# harness that silently ran ZERO cases must fail here rather than report a pass,
# because "0 failed" and "nothing executed" are the same exit code.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
HARNESS="$REPO_ROOT/.claude/hooks/stop/test-worklist-v5.sh"

if [[ ! -f "$HARNESS" ]]; then
    echo "FAIL: $HARNESS not found — this gate has nothing to run, which is a" >&2
    echo "failure rather than a pass: a vanished harness cannot be green." >&2
    exit 1
fi

OUTPUT=$(bash "$HARNESS" 2>&1) || {
    printf '%s\n' "$OUTPUT"
    echo "FAIL: stop-hook harness exited nonzero" >&2
    exit 1
}
printf '%s\n' "$OUTPUT"

# The harness ends with "  passed=<n> failed=<m>". Parse BOTH: trusting the exit
# code alone is what lets a harness that executed nothing look identical to one
# that executed everything and passed.
SUMMARY=$(grep -oE 'passed=[0-9]+ failed=[0-9]+' <<<"$OUTPUT" | tail -1)
if [[ -z "$SUMMARY" ]]; then
    echo "FAIL: could not find the harness summary line — it may have changed" >&2
    echo "shape, in which case this gate is no longer reading its result." >&2
    exit 1
fi
PASSED=$(sed -E 's/passed=([0-9]+).*/\1/' <<<"$SUMMARY")
FAILED=$(sed -E 's/.*failed=([0-9]+)/\1/' <<<"$SUMMARY")

if [[ "$FAILED" -ne 0 ]]; then
    echo "FAIL: stop-hook harness reported $FAILED failing case(s)" >&2
    exit 1
fi
if [[ "$PASSED" -lt 1 ]]; then
    echo "FAIL: stop-hook harness ran ZERO cases — a vacuous green, not a pass" >&2
    exit 1
fi

echo "PASS: stop-hook harness $SUMMARY"
