#!/usr/bin/env bash
#
# Gate: the mutation runner itself must keep working.
#
# WHAT THIS DOES AND DOES NOT PROTECT, stated plainly because the distinction is
# the whole reason this gate is small. It does NOT force anyone to run a mutation
# for every new test case; that is not gateable (see the rebuttal in
# agent/main/PLAN-promote-mutation-runner.md, section "Gate or tool?").
# What it protects is the INSTRUMENT: mutate-check.sh must keep producing the
# right verdict for each of its four outcomes, so it cannot silently rot into
# something that always says OK. An instrument nobody is forced to use is still
# worth having; an instrument that lies is worse than none.
#
# Every scenario runs against a miniature fixture suite, so the whole gate takes
# seconds rather than the 8-plus minutes two passes of the real suite would cost.
#
# CONTROL-FIRST BY CONSTRUCTION: scenario 1 is the only one that may exit 0. If
# the runner's logic collapsed into "always succeed", scenarios 2, 3 and 4 would
# all fail this gate. If it collapsed into "always fail", scenario 1 would.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
RUNNER="$ROOT/.ci/scripts/test/mutate-check.sh"
FIXDIR="$ROOT/.ci/scripts/test/fixtures/mutate-check"
SUITE="$FIXDIR/fixture-suite.sh"
TARGET="$FIXDIR/fixture_mod.py"

FAILED=0
ok() { printf '  \033[0;32mok\033[0m   %s\n' "$1"; }
bad() {
    printf '  \033[0;31mFAIL\033[0m %s\n' "$1"
    [[ -n "${2:-}" ]] && sed 's/^/       /' <<<"$2" | head -12
    FAILED=$((FAILED + 1))
}

for f in "$RUNNER" "$SUITE" "$TARGET"; do
    [[ -f "$f" ]] || {
        echo "check-mutate-check: missing $f" >&2
        exit 1
    }
done

echo "info: exercising mutate-check.sh through all four verdicts"

# 1. The good case: mutation kills case 900, baseline is clean. The ONLY exit 0.
OUT="$("$RUNNER" --suite "$SUITE" --file "$TARGET" \
    --from 'GUARD_ENABLED = True' --to 'GUARD_ENABLED = False' \
    --expect-red 900 2>&1)"
RC=$?
if [[ "$RC" -eq 0 ]] && grep -qF "Both directions hold" <<<"$OUT"; then
    ok "red-then-green exits 0"
else
    bad "red-then-green did not exit 0 (rc=$RC)" "$OUT"
fi

# 2. THE VERDICT THIS TOOL EXISTS FOR. Case 901 is red in both directions, so
# its red proves nothing about the defect. Reporting this as success is the
# precise failure that cost a session hours, so it is the load-bearing scenario.
OUT="$(MUTCHK_FIXTURE_ALWAYS_BROKEN=1 "$RUNNER" --suite "$SUITE" --file "$TARGET" \
    --from 'GUARD_ENABLED = True' --to 'GUARD_ENABLED = False' \
    --expect-red 901 2>&1)"
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "PROVED NOTHING" <<<"$OUT"; then
    ok "red in BOTH directions is reported as PROVED NOTHING, not success"
else
    bad "a case red in both directions was not caught (rc=$RC)" "$OUT"
fi

# 3. A mutation that applies cleanly but changes nothing observable must be
# reported as an undetected defect, never as a pass.
OUT="$("$RUNNER" --suite "$SUITE" --file "$TARGET" \
    --from '"unmutated"' --to '"mutated-but-harmless"' \
    --expect-red 900 2>&1)"
RC=$?
if [[ "$RC" -ne 0 ]] && grep -qF "does not detect this defect" <<<"$OUT"; then
    ok "a mutation the suite cannot see is reported as undetected"
else
    bad "an undetected mutation was not reported (rc=$RC)" "$OUT"
fi

# 4. A --from string that is absent is a HARD ERROR. If it were a warning, the
# run would proceed with an unmutated sandbox, the mutant would come back green,
# and that reads exactly like scenario 3: indistinguishable from a real finding.
OUT="$("$RUNNER" --suite "$SUITE" --file "$TARGET" \
    --from 'this string is nowhere in the fixture' --to 'x' \
    --expect-red 900 2>&1)"
RC=$?
if [[ "$RC" -eq 2 ]] && grep -qF "MUTATION DID NOT APPLY" <<<"$OUT"; then
    ok "a no-op mutation is a hard error, not a silent green"
else
    bad "a no-op mutation was not a hard error (rc=$RC)" "$OUT"
fi

# 5. The runner's own first bug: `^FAIL` matches nothing because the suite
# indents, so a failing run printed an empty failure list. The fixture prints
# indented lines exactly like the real suite, so scenario 1 passing at all
# proves the indentation-aware matching still works. Asserted explicitly so the
# reason this fixture indents cannot be lost to a future tidy-up.
if grep -qE '^\s+echo "  (PASS|FAIL): ' "$SUITE"; then
    ok "the fixture prints INDENTED result lines, as the real suite does"
else
    bad "the fixture stopped indenting; the ^ *FAIL regression is unguarded"
fi

echo
if [[ "$FAILED" -eq 0 ]]; then
    printf '\033[0;32m✓\033[0m mutate-check.sh produces the right verdict in all four outcomes\n'
    exit 0
fi
printf '\033[0;31m✗\033[0m %d mutate-check.sh self-test(s) failed\n' "$FAILED"
exit 1
