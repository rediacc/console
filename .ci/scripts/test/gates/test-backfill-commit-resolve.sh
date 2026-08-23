#!/bin/bash
# Both-ways test for .ci/scripts/release/resolve-backfill-commit.sh -- the step
# that decides which commit a backfilled release sentinel records.
#
# WHY THIS CLASS NEEDS A GATE. The script had none, and its only caller is a
# manually-dispatched workflow (.github/workflows/backfill-release-sentinel.yml:109),
# so its failure paths are seen by a human roughly never -- and then only by a
# human already mid-incident, reading the message to decide what went wrong.
# A wrong message there does not fail loudly; it sends the investigation
# somewhere else.
#
# THE DEFECT THIS PINS. `git merge-base --is-ancestor` returns non-zero for two
# unrelated situations: a commit that exists but sits off main, and a SHA that
# is not an object in this repository at all. Git's own "Not a valid object
# name" for the second went to a `2>/dev/null`, so BOTH produced
# "commit <sha> is not reachable from origin/main" -- which reads as a real tag
# pointing somewhere odd. After the 2026-08-23 history rewrite the second case
# is the likely one, because any SHA copied out of an old release note or an R2
# sentinel no longer exists.
#
# HOW. Every case runs the REAL script (not a copy) with its working directory
# set to a purpose-built synthetic repository, so the git behaviour under test
# is git's, not a fake's. The one exception is the anti-swallow control, which
# needs a deliberately broken copy and says so.
#
# EXIT CODES ARE PART OF THE CONTRACT. This was a diagnosis change, not a
# control-flow change, so every case asserts the exit code as well as the text.
# A "clearer message" that also changed which inputs are accepted would be a
# different and much worse change.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

UNDER_TEST="$REPO_ROOT/.ci/scripts/release/resolve-backfill-commit.sh"

NOT_A_COMMIT="does not name a commit in this repository"
DETACHED="refusing to backfill a sentinel for a detached tag"
GHOST_SHA="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

LAST_OUT=""
LAST_RC=0

[ -x "$UNDER_TEST" ] || log_fail "$UNDER_TEST is not executable"
REAL_GIT="$(command -v git)" || log_fail "git is not on PATH; this gate drives real git deliberately"

# make_repo <dir> -- a repository with, deliberately:
#   * main, with origin/main pointing at its tip
#   * v1.0.0 on main            (reachable)
#   * v9.9.9 on an off-main commit that REALLY EXISTS (detached, not a ghost)
# The detached commit is the whole point: it is the case the new existence
# probe could plausibly break by re-classifying it as "does not exist".
make_repo() {
    local d="$1"
    mkdir -p "$d"
    git -C "$d" init -q
    git -C "$d" config user.email test@example.invalid
    git -C "$d" config user.name test
    git -C "$d" config commit.gpgsign false
    echo base >"$d/f"
    git -C "$d" add f
    git -C "$d" commit -qm base
    git -C "$d" branch -q -M main
    git -C "$d" tag v1.0.0 main
    git -C "$d" update-ref refs/remotes/origin/main HEAD
    git -C "$d" checkout -q -b side
    echo off-main >"$d/f"
    git -C "$d" commit -qam "off main"
    git -C "$d" tag v9.9.9
    git -C "$d" checkout -q main
}

# detached_sha <dir> -- the real, existing, off-main commit.
detached_sha() {
    git -C "$1" rev-list -n1 v9.9.9
}

# run_resolve <repo-dir> <script> [KEY=VALUE ...]
run_resolve() {
    local repo="$1" script="$2"
    shift 2
    local rc=0
    LAST_OUT="$(cd "$repo" && env \
        VERSION=v9.9.9 \
        GITHUB_OUTPUT="$repo/step-output" \
        NO_COLOR=1 \
        "$@" \
        bash "$script" 2>&1)" || rc=$?
    LAST_RC="$rc"
    return 0
}

step_output() {
    [[ -f "$1/step-output" ]] && cat "$1/step-output" || true
}

# ---------------------------------------------------------------------------

test_a_nonexistent_sha_is_named_as_nonexistent() {
    # FIRE. The post-rewrite case: a SHA pasted from an old release note or an
    # R2 sentinel, which is not in the repository at all.
    local t="$1"
    make_repo "$t/repo"
    run_resolve "$t/repo" "$UNDER_TEST" INPUT_SHA="$GHOST_SHA"
    assert_exit_code 1 "$LAST_RC" "a SHA that does not exist must still fail, and fail the same way it always did"
    assert_contains "$LAST_OUT" "$NOT_A_COMMIT" "it says the SHA does not name a commit here"
    assert_contains "$LAST_OUT" "no such object exists here at all" \
        "in words that stop the operator hunting for a detached tag"
    assert_contains "$LAST_OUT" "2026-08-23 git history rewrite" "and names the rewrite that most likely caused it"
    assert_not_contains "$LAST_OUT" "$DETACHED" \
        "and must NOT claim a detached tag, which is the misdiagnosis this fix exists to remove"
    assert_eq "$(step_output "$t/repo")" "" "nothing is written to the step output on a failure"
    log_pass "FIRE: a non-existent SHA is diagnosed as non-existent, not as a detached tag"
}

test_a_real_but_detached_sha_still_says_detached() {
    # THE CONTROL THAT MATTERS. This is the case the existence probe could
    # plausibly break: a commit that genuinely exists and genuinely is off main.
    # If the probe were too broad -- a bare `cat-file -e` on the wrong argument,
    # or the check applied to the tag path -- this would flip to the
    # not-an-object message and the fix would have traded one misdiagnosis for
    # another.
    local t="$1"
    make_repo "$t/repo"
    local sha
    sha="$(detached_sha "$t/repo")"
    run_resolve "$t/repo" "$UNDER_TEST" INPUT_SHA="$sha"
    assert_exit_code 1 "$LAST_RC" "a detached commit still fails, with the same exit code as before"
    assert_contains "$LAST_OUT" "$DETACHED" "and is still diagnosed as a detached tag"
    assert_contains "$LAST_OUT" "not reachable from origin/main" "naming reachability, which IS the real problem here"
    assert_not_contains "$LAST_OUT" "$NOT_A_COMMIT" \
        "and must NOT claim the commit is missing -- it is right there, just not on main"
    assert_not_contains "$LAST_OUT" "2026-08-23" "nor blame the history rewrite for an ordinary detached tag"
    log_pass "CONTROL: a real-but-detached SHA keeps the detached diagnosis"
}

test_the_tag_path_is_untouched_by_the_probe() {
    # The probe is scoped to the operator-supplied path. A detached TAG resolved
    # through :41 must behave exactly as it did before this change: existing
    # commit, off main, detached message.
    local t="$1"
    make_repo "$t/repo"
    run_resolve "$t/repo" "$UNDER_TEST"
    assert_exit_code 1 "$LAST_RC" "the tag path still rejects a detached tag"
    assert_contains "$LAST_OUT" "resolved v9.9.9" "having resolved the tag itself"
    assert_contains "$LAST_OUT" "$DETACHED" "with the detached diagnosis"
    assert_not_contains "$LAST_OUT" "$NOT_A_COMMIT" "and no existence complaint about a tag it just resolved"
    log_pass "CONTROL: the tag path is unchanged -- the probe never runs there"
}

test_a_non_commit_object_is_rejected() {
    # THE `^{commit}` PEEL. A tree SHA is a perfectly real object, so a bare
    # `cat-file -e <sha>` waves it through -- and it then fails reachability and
    # gets reported as a DETACHED TAG, which is the same misdiagnosis one layer
    # down. The peel is what stops that, and without this case nothing in the
    # repo would notice if somebody simplified it away.
    local t="$1"
    make_repo "$t/repo"
    local tree_sha
    tree_sha="$(git -C "$t/repo" rev-parse "main^{tree}")"
    run_resolve "$t/repo" "$UNDER_TEST" INPUT_SHA="$tree_sha"
    assert_exit_code 1 "$LAST_RC" "a tree SHA is not backfillable and must fail"
    assert_contains "$LAST_OUT" "$NOT_A_COMMIT" "and is diagnosed as not naming a commit"
    assert_contains "$LAST_OUT" "the object is not a commit" \
        "with the message covering this half of the probe, not just the missing-object half"
    assert_not_contains "$LAST_OUT" "$DETACHED" \
        "and must NOT be reported as a detached tag, which is what a bare cat-file -e would produce"

    # CONTROL: the COMMIT that owns that very tree is accepted, so the rejection
    # above is about the object's type and not about that repository.
    rm -f "$t/repo/step-output"
    local commit_sha
    commit_sha="$(git -C "$t/repo" rev-list -n1 main)"
    run_resolve "$t/repo" "$UNDER_TEST" VERSION=v1.0.0 INPUT_SHA="$commit_sha"
    assert_exit_code 0 "$LAST_RC" "CONTROL: the commit holding that tree resolves fine"
    log_pass "a tree SHA is rejected as not-a-commit (control: its own commit is accepted)"
}

test_a_reachable_commit_still_succeeds() {
    # CONTROL for the happy path, both ways in. If this broke, the gate above
    # would be asserting that a script which rejects everything is correct.
    local t="$1"
    make_repo "$t/repo"
    local main_sha
    main_sha="$(git -C "$t/repo" rev-list -n1 main)"

    run_resolve "$t/repo" "$UNDER_TEST" VERSION=v1.0.0
    assert_exit_code 0 "$LAST_RC" "a reachable tag exits 0"
    assert_contains "$(step_output "$t/repo")" "commit_sha=$main_sha" "and writes the commit to the step output"
    assert_contains "$LAST_OUT" "commit reachable from origin/main" "and says so"

    rm -f "$t/repo/step-output"
    run_resolve "$t/repo" "$UNDER_TEST" VERSION=v1.0.0 INPUT_SHA="$main_sha"
    assert_exit_code 0 "$LAST_RC" "a reachable operator-supplied SHA also exits 0 -- the probe passes an existing commit through"
    assert_contains "$(step_output "$t/repo")" "commit_sha=$main_sha" "and it too is written out"
    log_pass "CONTROL: a reachable commit exits 0 and writes commit_sha, from both paths"
}

test_a_missing_tag_is_unchanged() {
    # The one other failure path in the script. It must not have moved.
    local t="$1"
    make_repo "$t/repo"
    run_resolve "$t/repo" "$UNDER_TEST" VERSION=v4.5.6
    assert_exit_code 1 "$LAST_RC" "an unknown tag still exits 1"
    assert_contains "$LAST_OUT" "tag v4.5.6 not found in this checkout" "with its own message"
    assert_not_contains "$LAST_OUT" "$NOT_A_COMMIT" "and not the new one"
    log_pass "CONTROL: the missing-tag path is untouched"
}

# ---------------------------------------------------------------------------
# ANTI-SWALLOW
#
# The `2>/dev/null` on the reachability check is what hid this defect for as
# long as it existed. The property that matters is not "there is a probe" but
# "the two situations reach the operator as DIFFERENT diagnoses". Asserting the
# outcome rather than the mechanism means a future rewrite that keeps the
# property passes, and one that re-swallows the distinction fails, however it
# is spelled.
# ---------------------------------------------------------------------------

# Prints one line per violation; empty output means the two diagnoses differ.
# Compares only ::error:: lines: the informational echoes name the SHA, so raw
# outputs always differ and comparing them would make this vacuous.
swallowed_distinction() {
    local ghost_out="$1" detached_out="$2"
    local a b
    a="$(printf '%s\n' "$ghost_out" | grep -a '::error::' | sed "s/$GHOST_SHA/<SHA>/g; s/[0-9a-f]\{40\}/<SHA>/g" || true)"
    b="$(printf '%s\n' "$detached_out" | grep -a '::error::' | sed "s/[0-9a-f]\{40\}/<SHA>/g" || true)"
    if [[ -z "$a" || -z "$b" ]]; then
        echo "one of the two failure paths emitted no ::error:: line at all, so there is nothing for an operator to read"
        return 0
    fi
    if [[ "$a" == "$b" ]]; then
        echo "a non-existent SHA and a real-but-detached SHA produce IDENTICAL operator-visible errors, so the distinction is swallowed"
    fi
}

test_the_two_failures_are_distinguishable() {
    local t="$1"
    make_repo "$t/repo"
    local sha ghost_out detached_out found
    sha="$(detached_sha "$t/repo")"

    run_resolve "$t/repo" "$UNDER_TEST" INPUT_SHA="$GHOST_SHA"
    ghost_out="$LAST_OUT"
    run_resolve "$t/repo" "$UNDER_TEST" INPUT_SHA="$sha"
    detached_out="$LAST_OUT"

    found="$(swallowed_distinction "$ghost_out" "$detached_out")"
    [[ -z "$found" ]] || log_fail "resolve-backfill-commit.sh: $found"

    # CONTROL: reproduce the PRE-FIX behaviour and require it to be reported.
    #
    # Not by editing the script. An earlier version of this control cut the
    # probe block out of a copy with a regex, and that coupled the control to
    # the exact spelling of one `if` header: a harmless refactor made the regex
    # miss, and the gate died with a python traceback instead of a verdict.
    # Shimming `git` so `cat-file` cannot fail is behaviourally identical to
    # having no probe at all, costs nothing when the script is rewritten, and
    # exercises the REAL script rather than a mutant of it.
    mkdir -p "$t/nogit"
    cat >"$t/nogit/git" <<SHIM
#!/bin/bash
# Pre-fix simulator: an existence probe that cannot fail. Everything else is
# real git, so the reachability check behaves exactly as it does in production.
[[ "\${1:-}" == "cat-file" ]] && exit 0
exec "$REAL_GIT" "\$@"
SHIM
    chmod +x "$t/nogit/git"

    run_resolve "$t/repo" "$UNDER_TEST" PATH="$t/nogit:$PATH" INPUT_SHA="$GHOST_SHA"
    ghost_out="$LAST_OUT"
    run_resolve "$t/repo" "$UNDER_TEST" PATH="$t/nogit:$PATH" INPUT_SHA="$sha"
    detached_out="$LAST_OUT"
    found="$(swallowed_distinction "$ghost_out" "$detached_out")"
    [[ -n "$found" ]] || log_fail "CONTROL FAILED: with the existence probe neutralised -- the pre-fix behaviour, which reported both failures identically -- nothing was reported, so this check cannot detect a re-swallow"
    assert_contains "$found" "IDENTICAL operator-visible errors" "and the control names what it found"
    log_pass "the two failures reach the operator as different diagnoses (control: the pre-fix script IS reported)"
}

log_test "test-backfill-commit-resolve"
with_temp_dir test_a_nonexistent_sha_is_named_as_nonexistent
with_temp_dir test_a_real_but_detached_sha_still_says_detached
with_temp_dir test_the_tag_path_is_untouched_by_the_probe
with_temp_dir test_a_non_commit_object_is_rejected
with_temp_dir test_a_reachable_commit_still_succeeds
with_temp_dir test_a_missing_tag_is_unchanged
with_temp_dir test_the_two_failures_are_distinguishable
echo ""
log_pass "all tests passed"
