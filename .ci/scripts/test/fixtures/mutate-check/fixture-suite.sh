#!/usr/bin/env bash
# A miniature stand-in for test-worklist-v5.sh, used only to exercise
# mutate-check.sh. It prints the same `  PASS: <id> ...` / `  FAIL: <id> ...`
# shape, indented exactly as the real suite does, because that indentation is
# what the runner's `^ *FAIL` matching depends on and a fixture that printed
# unindented lines would let the original `^FAIL` bug back in unnoticed.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILED=0

if grep -q '^GUARD_ENABLED = True$' "$DIR/fixture_mod.py"; then
    echo "  PASS: 900 the guard is enabled"
else
    echo "  FAIL: 900 the guard is disabled"
    FAILED=$((FAILED + 1))
fi

# Case 901 models a case that can NEVER pass, which is the situation the whole
# two-direction rule exists for. Driven by an environment variable rather than a
# marker file so the gate never has to mutate the real tree and never has a
# cleanup step a kill could skip.
if [[ "${MUTCHK_FIXTURE_ALWAYS_BROKEN:-0}" == "1" ]]; then
    echo "  FAIL: 901 this case can never pass, in either direction"
    FAILED=$((FAILED + 1))
else
    echo "  PASS: 901 this case is healthy"
fi

echo "  passed=$((2 - FAILED)) failed=$FAILED"
[[ "$FAILED" -eq 0 ]]
