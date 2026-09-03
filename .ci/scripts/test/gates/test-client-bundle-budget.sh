#!/bin/bash
# Drives scripts/check-client-bundle-budget.ts and, crucially, a MUTANT of it.
#
# WHY THIS EXISTS. That gate was green for as long as it had existed while
# under-reporting the homepage by 124,673 B. `importSpecifiers` required whitespace
# after `import`, which minified side-effect imports do not have
# (`import"./x.js";import"./y.js";`), so the walk dead-ended at a 129-byte facade
# chunk and never saw the 122,110 B video player every homepage visitor downloads.
# It reported 451,621 B for a page shipping 576,294 B, and printed a checkmark.
#
# The gate's own fixture is why nothing caught it: it only ever wrote
# `import { x } from "./heavy.js"` -- spaced, and via `from`. A fixture that never
# writes the shape the real bundler emits cannot fail on it.
#
# So the case that matters here is the MUTANT: revert the one character and the
# selftest must go red and NAME the facade plant. Without it the plants are
# unfalsifiable, and their first draft genuinely was -- they asserted on chunks the
# fixture already reached by another path, so they passed against the very defect
# they were written for. That is what this file caught.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/scripts/check-client-bundle-budget.ts"
DIST="$REPO_ROOT/packages/www/dist"

# ── 1. The gate's own selftest is green ────────────────────────────────────
test_selftest_green() {
    local rc=0 out
    out="$(cd "$REPO_ROOT" && npx tsx "$GATE" --selftest 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "the gate's selftest must pass on a clean tree"
    assert_contains "$out" "no-space side-effect facade" "and exercise the facade shape"
    assert_contains "$out" "ONLY through such a facade" "and the dynamic edge behind it"
    log_pass "the selftest covers the shape that hid 124,673 B"
}

# ── 2. THE MUTANT. The control that proves the controls can fail. ──────────
test_mutant_reverts_the_fix() {
    # The mutant lives OUTSIDE the repo. Writing it to scripts/ was the first draft and
    # check:ci-pool-writer-safety caught it: run-all.sh would then schedule this file in
    # the shared pool beside tests that read the same paths. The gate imports only node
    # builtins plus @rediacc/locales, so a symlinked node_modules is all it needs to
    # resolve -- the same trick test-gate-anti-vacuity.sh uses for its fixture tree.
    local work mutant
    work="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expanding now binds this specific path into the trap so RETURN removes the right directory
    trap "rm -rf '$work'" RETURN
    ln -s "$REPO_ROOT/node_modules" "$work/node_modules"
    mutant="$work/mutant.ts"
    sed 's|/\\bimport\\s\*\["'"'"'\]|/\\bimport\\s+["'"'"']|' "$GATE" >"$mutant"
    # VACUITY GUARD: if the sed stopped matching, the mutant is the gate itself and
    # a green run below would mean nothing.
    grep -q 'import\\s+\["' "$mutant" ||
        log_fail "the mutation did not apply; this control would be testing the unmutated gate"

    local rc=0 out
    out="$(cd "$REPO_ROOT" && npx tsx "$mutant" --selftest 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "reverting \\s* to \\s+ must make the selftest FAIL"
    assert_contains "$out" "FAIL  PLANT: a no-space side-effect facade" "naming the facade plant"
    log_pass "CONTROL: the plants detect the exact defect, not merely pass beside it"
}

# ── 3. ANTI-VACUITY against the real build, when one exists ────────────────
# 49 no-space edges across 20 files in the dist as measured on 2026-09-03. A floor
# of one is anti-vacuous and goes red the instant the regex regresses. Absent dist
# is a LOUD skip, never a silent pass.
test_real_dist_has_the_shape() {
    if [[ ! -d "$DIST" ]]; then
        log_pass "SKIP (loudly): packages/www/dist absent, so the real-build arm asserted NOTHING"
        return 0
    fi
    # No 2>/dev/null: check:ci-silent-failures is right that discarding stderr here would
    # turn "the dist moved" into "zero edges", which is the vacuous answer this arm exists
    # to refuse. Missing directories are handled by testing for them.
    local n=0 d c
    for d in assets scripts; do
        [[ -d "$DIST/$d" ]] || continue
        # `|| true` on the ASSIGNMENT, not on grep: under `set -o pipefail` a grep that
        # matches nothing exits 1 and would kill the script. Zero matches is data here --
        # and it is the data that makes this arm FAIL below, which is the point.
        c="$(grep -rohE 'import"[^"]+"' "$DIST/$d" | wc -l)" || true
        n=$((n + c))
    done
    [[ "$n" -ge 1 ]] ||
        log_fail "found $n no-space side-effect edge(s) in the real dist; this gate's whole subject is gone, so its green would mean nothing"
    log_pass "the real build still emits the shape ($n edge(s)); the fix is not measuring a fixture only"
}

log_test "test-client-bundle-budget"
test_selftest_green
test_mutant_reverts_the_fix
test_real_dist_has_the_shape

echo ""
log_pass "all tests passed"
