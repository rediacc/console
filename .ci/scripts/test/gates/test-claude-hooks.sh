#!/bin/bash
# CI wrapper for the Claude hook harness (.claude/hooks/test-hooks.sh).
#
# The pre-bash hooks carry live PR policy — draft-only creation, green-gated
# `gh pr ready`, the `--admin` merge ban, merge-time review hygiene — and the
# harness (41 offline cases: quote-strip evasion, command-position anchoring,
# prose false-positive controls) previously ran only when someone remembered
# to run it. A hook regression could never turn CI red. run-all.sh discovers
# this wrapper like any other gate test, which also puts the harness inside
# `npm run ci` via check:ci-quality-gates.
#
# The harness is offline by design (network verification paths in the hooks
# are explicitly out of its scope), so it is safe and fast here.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

# run-all.sh's vacuous-test guard counts `PASS:` lines; the harness speaks
# `ok [..]` + a final `PASS=<n> FAIL=<m>` counter. Translate rather than
# trust the exit code alone: require FAIL=0 AND a nonzero case count, so a
# harness that silently ran nothing still fails this gate.
OUTPUT=$(bash "$REPO_ROOT/.claude/hooks/test-hooks.sh" 2>&1) || {
    printf '%s\n' "$OUTPUT"
    echo "FAIL: claude-hook harness exited nonzero" >&2
    exit 1
}
printf '%s\n' "$OUTPUT"

SUMMARY=$(printf '%s\n' "$OUTPUT" | grep -E '^PASS=[0-9]+ FAIL=[0-9]+$' | tail -1)
CASES=$(printf '%s' "$SUMMARY" | sed -n 's/^PASS=\([0-9]*\) FAIL=.*/\1/p')
FAILS=$(printf '%s' "$SUMMARY" | sed -n 's/.*FAIL=\([0-9]*\)$/\1/p')

if [[ -z "$CASES" || -z "$FAILS" || "$FAILS" != "0" || "$CASES" -eq 0 ]]; then
    echo "FAIL: harness summary missing or red (got: '${SUMMARY:-none}')" >&2
    exit 1
fi

echo "PASS: claude-hook harness green ($CASES offline cases)"
