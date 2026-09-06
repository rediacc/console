#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# needs: none
# lane: quality-security
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# why: Test for scripts/lib/policy-paths.ts -- the ONE seam that says where a suppression policy file lives
# ---- end gate ----

# Test for scripts/lib/policy-paths.ts -- the ONE seam that says where a
# suppression policy file lives.
#
# WHY THE SEAM EXISTS, AND WHAT IT WAS FOR. FIFTEEN allow / block / exempt files
# used to sit at the repository root with their readers mostly hard-coding it;
# four of them (.audit-allowlist, .audit-prod-allowlist, .deps-upgrade-blocklist
# in .ci/scripts/security/audit.sh, plus .profiler-coverage-allowlist in
# check-profiler-coverage.sh) read a BARE RELATIVE NAME and were correct only
# because the script happens to `cd` to the repo root first.
#
# THE MOVE LANDED 2026-09-06 at b80552370: POLICY_DIR is `.ci/policy` and all
# fifteen are there. `.ci-trigger` stayed at root with its own recorded reason.
# The seam earned itself twice over on the way: the readers had to travel in one
# change, and when a commit landed the renames WITHOUT them, the half-landed
# state was exactly what the seam is written to refuse.
#
# THE THREE PROPERTIES THIS FILE PINS, each of them a refusal:
#
#   1. PURE JOIN. policyPath() never touches the filesystem, so it answers the
#      same string against a root that contains nothing at all. A caller that
#      cannot find the file gets its own ENOENT at its own path, instead of the
#      helper quietly resolving somewhere else.
#   2. NO FALLBACK. There is exactly one location at a time. A helper that tried
#      the new location and fell back to the old one is precisely how a move
#      half-lands with every gate still green.
#   3. LOUD REFUSAL. An unknown name throws and names the valid set. Returning a
#      plausible path for a typo would be read by every consumer here as an empty
#      allowlist, which is indistinguishable from "nothing is suppressed".
#
# Plus one liveness assertion that keeps the name list honest: every name the
# module knows must resolve to a file that is actually there TODAY. That is what
# turns the move into a one-line change instead of a hope.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

LIB="$REPO_ROOT/scripts/lib/policy-paths.ts"

# The module's own CLI, driven directly. An earlier version of this file
# generated a temp .ts importing the module; that needed four more exports than
# any TypeScript caller wants, and `lint:unused` was right to refuse them. Stdout
# and stderr are kept SEPARATE throughout, because `npx` prints an unrelated
# "Unknown project config minimum-release-age" warning on stderr and the first
# run of this file compared a path against that warning. The workspace tsx binary
# is called directly, which also skips npx's re-resolution.
pp() { (cd "$REPO_ROOT" && "$REPO_ROOT/node_modules/.bin/tsx" "$LIB" "$@"); }

test_pure_join_needs_no_filesystem() {
    local empty out
    empty="$(mktemp -d)"
    # Deliberately EMPTY: no .ci, no .ci/policy, no dotfiles, nothing. A helper
    # that stat'ed anything would have to either throw or answer a second
    # location here; a pure join cannot tell the difference and says so.
    out=$(pp --path .deps-upgrade-blocklist --root "$empty")
    assert_eq "$out" "$empty/.ci/policy/.deps-upgrade-blocklist" \
        "resolves against a root containing no .ci directory at all"
    # rmdir IS the second assertion: it refuses a non-empty directory, so a
    # helper that had touched, cached or created anything under the fixture root
    # would fail this line. Written this way rather than as `find | wc -l`
    # because check:ci-silent-failures refuses an unguarded pipeline here, and it
    # is right to -- a find that errored would count 0 and read as success.
    assert_eq "$(rmdir "$empty" 2>/dev/null && echo empty || echo not-empty)" "empty" \
        "and the fixture root is still empty, so nothing was created either"
    log_pass "policyPath is a pure join: no stat, no readdir, no fallback"
}

test_every_known_name_resolves_to_a_real_file() {
    local missing="" n=0 p
    # The liveness half. A name that resolves to nothing is a reader pointed at a
    # file that is not there, which every mechanism in this repo reads as an
    # empty list.
    #
    # ONE process, via --all-paths, not one per name. The obvious loop calling
    # `pp --path "$name"` fifteen times cost fifteen node startups and made this
    # the third-slowest gate in the whole quick lane; the answers are identical
    # because --all-paths is policyPath() mapped over the same name list.
    while IFS= read -r p; do
        n=$((n + 1))
        [[ -f "$p" ]] || missing="$missing $p"
    done < <(pp --all-paths)
    assert_eq "$missing" "" "every known policy name resolves to a file that exists today"
    # Anti-vacuity: an empty name list would pass the loop above without checking
    # anything, which is the whole class this repo keeps getting caught by.
    assert_eq "$((n >= 15))" "1" "and the name list is populated, so the loop asserted something"
    log_pass "all $n known policy names resolve to real files"
}

test_unknown_name_is_refused_loudly() {
    local out err rc=0 d
    d="$(mktemp -d)"
    pp --path .audit-allowlst >"$d/out" 2>"$d/err" || rc=$?
    out=$(cat "$d/out")
    err=$(cat "$d/err")
    rm -rf "$d"
    assert_eq "$rc" "2" "a typo is refused, not resolved"
    assert_eq "$out" "" "and nothing plausible is printed on stdout"
    assert_contains "$err" "is not a known policy file" "says what went wrong"
    assert_contains "$err" ".audit-allowlist" "names the valid set so the typo is obvious"
    assert_contains "$err" "POLICY_FILES" "names where to add a genuinely new one"
    log_pass "an unknown name is refused loudly, naming the valid set"
}

test_ci_trigger_is_not_a_policy_name() {
    # .ci-trigger is the one root dotfile in this family that is NOT moving. It
    # has no entries, no BLOCKER lines and no parser anywhere in the tree; its
    # only effect is ROOT_MANIFESTS membership in .ci/scripts/ci/scope-map.cjs,
    # which is what makes `touch .ci-trigger` force a full CI round. Naming it
    # here would make the module claim a file it must not move.
    assert_eq "$(pp --is .ci-trigger)" "false" \
        ".ci-trigger is not one of the names policyPath answers for"
    assert_eq "$(pp --is .deps-upgrade-blocklist)" "true" \
        "CONTROL: a name that IS policy answers true, so the check above is not always-false"
    assert_eq "$([[ -f "$REPO_ROOT/.ci-trigger" ]] && echo yes || echo no)" "yes" \
        "and it is still at the repository root, where its one gesture works"
    log_pass ".ci-trigger is excluded from the policy set and stays at the root"
}

test_one_location_at_a_time() {
    # NO TRANSITION FALLBACK. Every path the module hands out must live under the
    # single directory --dir names -- today the root, after the move .ci/policy.
    # Two live locations is the failure this asserts against.
    local dir expected strays="" p
    dir=$(pp --dir)
    expected="$REPO_ROOT"
    [[ -n "$dir" ]] && expected="$REPO_ROOT/$dir"
    while IFS= read -r p; do
        [[ "$(dirname "$p")" == "$expected" ]] || strays="$strays $p"
    done < <(pp --all-paths)
    assert_eq "$strays" "" "every policy path sits under exactly one directory"
    log_pass "there is exactly one live location ($expected), not two"
}

log_test "test-policy-path"
test_pure_join_needs_no_filesystem
test_every_known_name_resolves_to_a_real_file
test_unknown_name_is_refused_loudly
test_ci_trigger_is_not_a_policy_name
test_one_location_at_a_time
echo ""
log_pass "all tests passed"
