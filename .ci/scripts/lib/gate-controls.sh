#!/usr/bin/env bash
# The control-tally every shell gate here writes by hand.
#
# Extracted 2026-09-06 after check:ci-shape-duplication caught the same ~5 lines at
# three copies (check-release-key-canonical, check-release-signing-coverage,
# check-staging-tag-guard) and was right to: they ask the same question and only the
# label and values differ. Sourcing one copy also means a gate cannot quietly ship a
# tally that counts wrong.
#
# Usage:
#   source "$(dirname "${BASH_SOURCE[0]}")/../lib/gate-controls.sh"
#   gate_check "label" "$got" "$want"
#   gate_finish 3 "subject line"     # min-controls floor, then the verdict
GATE_FAILS=0
GATE_N=0

gate_check() {
    GATE_N=$((GATE_N + 1))
    if [[ "$2" == "$3" ]]; then
        echo "  ok    $1"
    else
        GATE_FAILS=$((GATE_FAILS + 1))
        echo "  FAIL  $1 (got '$2' want '$3')" >&2
    fi
}

# A battery that did not run is not a green one, which is why the floor is here and
# not left to each caller to remember.
gate_finish() {
    local min="$1" subject="$2"
    if ((GATE_N < min)); then
        echo "FAIL  only $GATE_N control(s) ran; the battery is not being executed as written" >&2
        GATE_FAILS=$((GATE_FAILS + 1))
    fi
    if ((GATE_FAILS)); then
        echo "✗ $subject: $GATE_FAILS of $GATE_N control(s) failed" >&2
        return 1
    fi
    echo "✓ $subject: $GATE_N control(s) passed"
    return 0
}
