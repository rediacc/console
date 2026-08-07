#!/bin/bash
# CI wrapper for the Stop-hook harnesses under .claude/hooks/stop/.
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
# WHY IT NOW RUNS TWO HARNESSES. test-report-inbox.sh (the durable sub-agent
# report inbox and the blocking waiter) was created with the EXACT problem quoted
# above: 74 cases that ran only when somebody typed them. Rather than let the
# same gap reopen under a second file name, this gate takes a LIST — so adding a
# third harness is one array entry and can never again mean "and a CI gate that
# nobody remembered to write".
#
# Modeled on test-claude-hooks.sh deliberately, down to the vacuity guard: a
# harness that silently ran ZERO cases must fail here rather than report a pass,
# because "0 failed" and "nothing executed" are the same exit code.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

# name:path. Every one must end with "  passed=<n> failed=<m>".
HARNESSES=(
    "stop-hook:$REPO_ROOT/.claude/hooks/stop/test-worklist-v5.sh"
    "report-inbox:$REPO_ROOT/.claude/hooks/stop/test-report-inbox.sh"
)

# ONE HARNESS PER INVOCATION, PARSED FROM ITS OWN OUTPUT. The single-harness
# version of this gate ended with `grep ... | tail -1`, which was correct while
# exactly one summary line existed and becomes a silent hazard the moment a
# second harness runs into the same buffer: tail -1 would read only the LAST
# summary and a red first harness would be reported green. Keeping each run in
# its own function makes that impossible by construction rather than by care.
run_harness() { # $1 name, $2 path
    local name="$1" harness="$2" output summary passed failed

    if [[ ! -f "$harness" ]]; then
        echo "FAIL[$name]: $harness not found — this gate has nothing to run," >&2
        echo "which is a failure rather than a pass: a vanished harness cannot be green." >&2
        return 1
    fi

    output=$(bash "$harness" 2>&1) || {
        printf '%s\n' "$output"
        echo "FAIL[$name]: harness exited nonzero" >&2
        return 1
    }
    printf '%s\n' "$output"

    # Parse the summary as well as the exit code: trusting the exit code alone is
    # what lets a harness that executed nothing look identical to one that
    # executed everything and passed.
    # `|| true` is required, not decorative: under `set -eo pipefail` a grep that
    # matches nothing aborts this assignment, so the explicit empty-check below
    # would never be reached and the script would die with no diagnostic at all —
    # the exact silent failure this gate exists to prevent, in the gate's own
    # wrapper. With it, an absent summary reaches the check and gets named.
    summary=$(grep -oE 'passed=[0-9]+ failed=[0-9]+' <<<"$output" | tail -1 || true)
    if [[ -z "$summary" ]]; then
        echo "FAIL[$name]: could not find the harness summary line — it may have" >&2
        echo "changed shape, in which case this gate is no longer reading its result." >&2
        return 1
    fi
    passed=$(sed -E 's/passed=([0-9]+).*/\1/' <<<"$summary")
    failed=$(sed -E 's/.*failed=([0-9]+)/\1/' <<<"$summary")

    if [[ "$failed" -ne 0 ]]; then
        echo "FAIL[$name]: harness reported $failed failing case(s)" >&2
        return 1
    fi
    if [[ "$passed" -lt 1 ]]; then
        echo "FAIL[$name]: harness ran ZERO cases — a vacuous green, not a pass" >&2
        return 1
    fi

    echo "PASS[$name]: $summary"
    return 0
}

# EVERY harness runs even after one fails, and the exit code is the OR. Stopping
# at the first failure would hide a second broken harness behind the first for as
# long as the first stayed broken.
rc=0
for entry in "${HARNESSES[@]}"; do
    if ! run_harness "${entry%%:*}" "${entry#*:}"; then
        rc=1
    fi
done

if [[ "$rc" -ne 0 ]]; then
    echo "FAIL: at least one stop-hook harness is red" >&2
    exit 1
fi
echo "PASS: all ${#HARNESSES[@]} stop-hook harnesses green"
