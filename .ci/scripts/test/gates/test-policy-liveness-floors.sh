#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# needs: none
# lane: quality-security
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# why: Test for the PER-PROBE INPUT FLOORS in scripts/gates/check-suppression-liveness.ts
# ---- end gate ----

# Test for the PER-PROBE INPUT FLOORS in scripts/gates/check-suppression-liveness.ts.
#
# THE HOLE THIS CLOSES. The gate's anti-vacuity guard keys on entriesChecked
# across the WHOLE run (isVacuous in scripts/lib/suppression-liveness.ts), so it
# only fires when the run asserted nothing AT ALL. The failure that actually
# happens is one list going empty while the other eleven stay full: the total
# stays healthy, the report still prints "every suppression entry is still
# load-bearing", and the probe over the emptied list has quietly stopped being a
# check. Measured on the real tree 2026-09-06: 12 probes, 87 entries, of which
# the largest single probe is 28 -- emptying any one of the others leaves a total
# that looks entirely normal.
#
# That is not a hypothetical. It is the shape the .ci/policy/ move creates: every
# mechanism in this repo treats "file not found" as "zero entries", which is
# indistinguishable from "nothing is suppressed", so a reader left pointing at
# the old location goes silent instead of failing.
#
# TWO FLOORS, TWO SHAPES, and this file proves each in both directions:
#
#   ENTRIES  the file is there but has been emptied  -> BELOW FLOOR
#   PRESENCE the file is not where the probe looks   -> MISSING FILE
#
# The presence floor only applies to a FULL CHECKOUT, because the gate's own test
# fixtures are deliberately partial. That predicate is the thing most likely to
# rot into a check that cannot fail, so it is asserted in BOTH directions here:
# the same missing file must be red in a full-shaped root and silent in a partial
# one, with nothing else changed between the two runs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/scripts/gates/check-suppression-liveness.ts"

# A fixture that is FULL-SHAPED (carries all three markers isFullCheckout looks
# for) and GREEN, so every later case changes exactly one thing.
#
# Each probe's file is present and satisfies its floor; the oracles are mostly
# left unavailable on purpose (no packages/, no go.mod, not a git repo) so those
# probes SKIP rather than condemn copied entries whose supporting tree is not
# here. Two probes do run for real -- deps against the root package.json, and
# parity-exempt against the copied workflow tree -- which is what keeps the run
# from being vacuous and the baseline from being green for the wrong reason.
make_full_fixture() {
    local t
    t="$(mktemp -d)"
    mkdir -p "$t/.ci/scripts/quality" "$t/.ci/config" "$t/.ci/policy" "$t/.github/workflows" \
        "$t/.github/actions/app-token" "$t/packages/json"

    # Marker 1 of 3: package.json. Also the deps probe's oracle.
    cp "$REPO_ROOT/package.json" "$t/package.json"
    # Marker 2 of 3: .ci/scripts/quality. Empty is fine; only its existence is read.
    # Marker 3 of 3: .github/workflows, and the parity-exempt probe's oracle. The
    # WHOLE directory, not just ci.yml: the exempt entries name gates stepped
    # from ci-quality.yml, and copying one workflow would condemn them all.
    cp "$REPO_ROOT"/.github/workflows/*.yml "$t/.github/workflows/" 2>/dev/null || true
    cp "$REPO_ROOT/.github/actions/app-token/action.yml" "$t/.github/actions/app-token/action.yml"

    local f
    for f in .deps-upgrade-blocklist .go-deps-upgrade-blocklist \
        .embed-assets-upgrade-blocklist .devcontainer-upgrade-blocklist \
        .unverified-download-allowlist .actions-upgrade-blocklist \
        .cli-i18n-orphan-allowlist .dead-bash-allowlist .ci-parity-exempt; do
        cp "$REPO_ROOT/.ci/policy/$f" "$t/.ci/policy/$f"
    done
    cp "$REPO_ROOT/packages/json/.templates-skiplist" "$t/packages/json/.templates-skiplist"
    cp "$REPO_ROOT/.ci/config/content-quality-allowlist.txt" "$t/.ci/config/content-quality-allowlist.txt"

    # The deps oracle here is the root manifest alone, so the copied blocklist's
    # entries -- declared in packages/*/package.json in the real tree -- would be
    # condemned as dead. Replace it with one entry the root manifest really does
    # declare, which keeps the probe RUNNING (that is the point) without a false
    # finding.
    printf '# BLOCKER: live package pinned deliberately so this fixture exercises the deps probe for real\neslint\n' >"$t/.ci/policy/.deps-upgrade-blocklist"

    # The content-quality probe's oracle is per-path existence, and creating
    # packages/json above is enough to make it RUN. Materialise the paths its
    # allowlist names, empty, so it runs and finds them live. Copying the
    # allowlist without them would have made the baseline red for a reason that
    # has nothing to do with input floors -- which is how a fixture ends up
    # proving something other than the property under test.
    local rel
    while read -r rel; do
        [[ -z "$rel" || "$rel" == \#* ]] && continue
        mkdir -p "$t/$(dirname "$rel")"
        : >"$t/$rel"
    done <"$t/.ci/config/content-quality-allowlist.txt"

    echo "$t"
}

run_gate() {
    local root="$1" n=0 y
    shift
    # ACTION_REFS_MIN_FILES matches the fixture's true .github corpus size rather
    # than switching the actions vacuity floor off; same reasoning as
    # test-suppression-liveness.sh. Counted with a glob rather than `find | wc`
    # because check:ci-silent-failures refuses an unguarded pipeline here, and
    # rightly: a find that matched nothing would silently make the floor 0.
    for y in "$root"/.github/workflows/*.yml "$root"/.github/actions/*/action.yml; do
        [[ -f "$y" ]] && n=$((n + 1))
    done
    (cd "$REPO_ROOT" && SUPPRESSION_LIVENESS_ROOT="$root" ACTION_REFS_MIN_FILES="$n" \
        "$REPO_ROOT/node_modules/.bin/tsx" "$GATE" "$@" 2>/dev/null) || return $?
}

# run_case <mutator> -- build a full-shaped fixture, let <mutator> change exactly
# one thing about it, run the gate, and leave the verdict in CASE_RC / CASE_OUT.
#
# EXTRACTED, not repeated. Each case below is a fixture, one mutation and a set
# of assertions, and writing that out per case produced five near-identical
# five-line preambles -- which check:ci-shape-duplication correctly reported as
# one piece of scaffolding wearing five names. Keeping it in one place also means
# a case cannot quietly forget to clean up its temp tree.
CASE_RC=0
CASE_OUT=""
run_case() {
    local mutate="$1" t
    t="$(make_full_fixture)"
    "$mutate" "$t"
    CASE_RC=0
    CASE_OUT=$(run_gate "$t") || CASE_RC=$?
    rm -rf "$t"
}

no_mutation() { :; }

# ONE list emptied, in place, keeping its comment header -- the shape a bad edit
# or a truncating rewrite leaves behind. Every other probe is untouched, so the
# run's TOTALS still look healthy; only the per-probe floor can see it.
mutate_empty_one_list() {
    printf '# BLOCKER: header left behind by an edit that dropped every entry beneath it\n' \
        >"$1/.ci/policy/.deps-upgrade-blocklist"
}

# The move hazard, exactly: the file is gone from where the probe looks. Its
# probe would parse zero entries and report a clean list.
mutate_remove_one_file() { rm -f "$1/.ci/policy/.cli-i18n-orphan-allowlist"; }

# The same removal, in a root that is no longer full-shaped -- one of the three
# markers isFullCheckout reads is taken away and nothing else changes.
mutate_remove_one_file_from_partial_root() {
    rm -f "$1/.ci/policy/.cli-i18n-orphan-allowlist"
    rm -rf "$1/.ci/scripts/quality"
}

test_real_tree_reports_per_probe_numbers() {
    local out rc=0
    out=$(cd "$REPO_ROOT" && "$REPO_ROOT/node_modules/.bin/tsx" "$GATE" 2>/dev/null) || rc=$?
    assert_exit_code 0 "$rc" "the live tree has no unmet input floor"
    assert_contains "$out" "Per-probe inputs" "prints the per-probe census"
    assert_contains "$out" "floor 1" "each row carries the floor it was judged against"
    assert_contains "$out" "probe(s)," "and a roll-up of probes and entries"
    assert_not_contains "$out" "BELOW FLOOR" "no probe is starved on the real tree"
    assert_not_contains "$out" "MISSING FILE" "no probe's file is missing on the real tree"

    # SELF-CONSISTENCY, so the census cannot drift from the run it describes: the
    # roll-up total must equal the sum of the rows it is a roll-up of. A hard-coded
    # 87 would be a hand-typed floor and would go red on the next legitimate edit.
    local rows_sum rollup
    rows_sum=$(awk '/ entries  floor /{ for (i = 1; i <= NF; i++) if ($(i+1) == "entries") s += $i } END { print s+0 }' <<<"$out")
    rollup=$(awk '/ probe\(s\), /{ for (i = 1; i <= NF; i++) if ($(i+1) == "entr(ies)") print $i }' <<<"$out")
    assert_eq "$rows_sum" "$rollup" "the roll-up equals the sum of the per-probe rows"
    log_pass "the real tree reports per-probe inputs, and the census adds up"
}

test_full_fixture_is_green() {
    run_case no_mutation
    assert_exit_code 0 "$CASE_RC" "the untouched full-shaped fixture must pass"
    assert_not_contains "$CASE_OUT" "BELOW FLOOR" "nothing starved in the baseline"
    assert_not_contains "$CASE_OUT" "MISSING FILE" "nothing missing in the baseline"
    assert_not_contains "$CASE_OUT" "vacuous" "and the baseline actually checked something"
    log_pass "baseline: a full-shaped fixture with every policy file passes"
}

test_emptying_one_list_fails() {
    run_case mutate_empty_one_list
    assert_exit_code 1 "$CASE_RC" "an emptied list must fail the gate"
    assert_contains "$CASE_OUT" "BELOW FLOOR" "the census marks the starved probe"
    assert_contains "$CASE_OUT" "the \"deps\" probe parsed 0 entr(ies)" "names the probe and the count"
    assert_contains "$CASE_OUT" "totals stay healthy" "explains why the totals did not catch it"
    assert_contains "$CASE_OUT" "minEntries to 0" "offers the legitimate-empty escape and where it lives"
    log_pass "emptying ONE list fails, even while the other probes stay full"
}

test_declared_empty_lists_do_not_fail() {
    # Three lists are DELIBERATELY empty in this repo (.actions-upgrade-blocklist,
    # .embed-assets-upgrade-blocklist, .devcontainer-upgrade-blocklist each say so
    # in their own header). The fixture copies them as-is, so this asserts the
    # floors distinguish "allowed to hold nothing" from "went empty" rather than
    # demanding every list be populated. No mutation: the baseline IS the case.
    run_case no_mutation
    assert_exit_code 0 "$CASE_RC" "declared-empty lists are not starvation"
    assert_contains "$CASE_OUT" "empty by design" "and they are labelled as such, not hidden"
    log_pass "a list that is allowed to hold nothing is not reported as starved"
}

test_missing_file_fails_in_a_full_checkout() {
    run_case mutate_remove_one_file
    assert_exit_code 1 "$CASE_RC" "a probe whose file is not there must fail the gate"
    assert_contains "$CASE_OUT" "MISSING FILE" "the census marks the missing input"
    assert_contains "$CASE_OUT" "is not at .ci/policy/.cli-i18n-orphan-allowlist" "names the path it looked at"
    assert_contains "$CASE_OUT" "policy-paths.ts" "points at the seam that moves a reader"
    log_pass "a policy file missing from a full checkout fails the gate"
}

test_missing_file_is_silent_in_a_partial_checkout() {
    # THE CONTROL FOR THE PREDICATE. Same deletion as the case above; the only
    # difference is that one of the three full-checkout markers is gone, so this
    # root is a fixture rather than a repository. If this run ALSO failed, the
    # gate's own fixtures could never be minimal; if the case above passed while
    # this one did too, the predicate would be satisfied by everything and the
    # presence floor would be decorative. Both directions have to hold.
    run_case mutate_remove_one_file_from_partial_root
    assert_exit_code 0 "$CASE_RC" "a partial root must not be judged for files it never had"
    assert_not_contains "$CASE_OUT" "MISSING FILE" "and says nothing about the missing file"
    log_pass "the same missing file is silent in a partial checkout (predicate control)"
}

test_undeclared_probe_is_refused() {
    local out rc=0
    # A probe with no PROBE_INPUT_FLOORS row is the one probe that would be free
    # to check nothing, so the gate refuses to run rather than treating silence as
    # exemption. Driven through --probe with a name no probe has, which is the
    # nearest reachable proof that the lookup is required rather than optional.
    out=$(cd "$REPO_ROOT" && "$REPO_ROOT/node_modules/.bin/tsx" "$GATE" --probe not-a-probe 2>&1) || rc=$?
    assert_exit_code 2 "$rc" "an unknown probe name is refused"
    assert_contains "$out" "unknown probe" "and named"
    log_pass "an unknown probe name is refused rather than silently running nothing"
}

log_test "test-policy-liveness-floors"
test_real_tree_reports_per_probe_numbers
test_full_fixture_is_green
test_emptying_one_list_fails
test_declared_empty_lists_do_not_fail
test_missing_file_fails_in_a_full_checkout
test_missing_file_is_silent_in_a_partial_checkout
test_undeclared_probe_is_refused
echo ""
log_pass "all tests passed"
