#!/bin/bash
# Both-ways test for the build-config hash in .ci/scripts/ci/generate-tag.sh.
#
# WHAT THE HASH IS FOR. `generate-tag.sh --submodule private/renet` mints the
# tag that names ghcr.io/rediacc/renet. initialize.sh asks the registry whether
# that tag already exists and, if it does, sets renet_exists=true, which skips
# the 45-minute Renet (Full) build AND the image build. The tag is therefore a
# cache key, and BUILD_CONFIG_FILES is its input list: an input missing from the
# list means a changed build resolves to an existing tag and a stale image is
# reused.
#
# WHAT BROKE. The list was consulted through `if [[ -f "$f" ]]`, so a renamed or
# moved input was skipped in silence. The one visible symptom is a cache miss --
# the surviving digests concatenate differently, so the tag still CHANGES -- and
# a cache miss is indistinguishable from normal behaviour. The list could rot
# indefinitely and the script would keep printing a plausible tag and exiting 0.
#
# This is not hypothetical: there are two build-renet.sh scripts in this repo,
# .ci/scripts/build/build-renet.sh (one CI step, and the one hashed here) and
# .ci/scripts/infra/build-renet.sh (nine CI steps, deliberately NOT hashed --
# see the comment on BUILD_CONFIG_FILES). A path swap between them is exactly
# the mistake the silent skip would have absorbed.
#
# WHY A FIXTURE TREE. The gate reads real files from the working directory, so
# the only way to plant a defect without touching a tracked file is to build a
# throwaway repo with the same shape and run the real script inside it.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/ci/generate-tag.sh"

FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT

ROOT="$FIXTURE/repo"

# Every path in BUILD_CONFIG_FILES, in the same order, relative to the tree
# root. Kept here so a list that grows without a test growing with it shows up
# in test_declared_inputs_match_the_script below rather than going unnoticed.
DECLARED_INPUTS=(
    "private/renet/Dockerfile"
    "private/renet/Dockerfile.native"
    "private/renet/build.sh"
    ".github/workflows/ci-build-renet.yml"
    ".github/workflows/ci-build-docker.yml"
    ".ci/scripts/build/build-renet.sh"
)

# The script under test resolves its lib relative to its own path, so mirror the
# .ci layout instead of copying the script somewhere flat.
build_fixture_tree() {
    rm -rf "$ROOT"
    mkdir -p "$ROOT/.ci/scripts/ci" "$ROOT/.ci/scripts/lib" \
        "$ROOT/.ci/scripts/build" "$ROOT/.ci/scripts/infra" \
        "$ROOT/.github/workflows" "$ROOT/private/renet"
    cp "$GATE" "$ROOT/.ci/scripts/ci/"
    cp "$REPO_ROOT"/.ci/scripts/lib/*.sh "$ROOT/.ci/scripts/lib/"

    local f
    for f in "${DECLARED_INPUTS[@]}"; do
        mkdir -p "$ROOT/$(dirname "$f")"
        printf 'seed content for %s\n' "$f" >"$ROOT/$f"
    done
    # The sibling that must NOT be an input. Present in the tree, as it is in
    # the real repo, so "the tag did not change" below is about the list and not
    # about a missing file.
    printf 'seed content for infra\n' >"$ROOT/.ci/scripts/infra/build-renet.sh"

    # A real git repo at the submodule path: the script rev-parses it, and a
    # fixed commit keeps the SUBMODULE_COMMIT half of the tag constant so every
    # difference below is attributable to the build-config half.
    git -C "$ROOT/private/renet" init -q .
    git -C "$ROOT/private/renet" add -A
    git -C "$ROOT/private/renet" \
        -c user.email=fixture@example.com -c user.name=fixture \
        commit -qm "fixture"
}

# tag -> prints the generated tag; fails the test if the script errors
tag() {
    local out rc=0
    out="$(cd "$ROOT" && .ci/scripts/ci/generate-tag.sh --submodule private/renet 2>/dev/null)" || rc=$?
    ((rc == 0)) || log_fail "generate-tag.sh exited $rc when a tag was expected"
    printf '%s' "$out"
}

# run_tag -> sets LAST_RC and LAST_OUT (not called in $(...): a subshell would
# strand both).
run_tag() {
    LAST_RC=0
    LAST_OUT="$(cd "$ROOT" && .ci/scripts/ci/generate-tag.sh --submodule private/renet 2>&1)" || LAST_RC=$?
}

# ---------------------------------------------------------------------------

test_declared_inputs_match_the_script() {
    # Anti-vacuity, and the first thing to break if someone extends the list.
    # Every case below is about DECLARED_INPUTS; if that drifts from the real
    # BUILD_CONFIG_FILES, the per-input control proof silently stops covering
    # the new entry.
    local body
    body="$(sed -n '/^    BUILD_CONFIG_FILES=(/,/^    )/p' "$GATE")"
    assert_contains "$body" 'BUILD_CONFIG_FILES=(' "the array must still be parseable from the script"
    local declared_count=0 f
    for f in "${DECLARED_INPUTS[@]}"; do
        # The array spells the submodule paths through $SUBMODULE_PATH.
        local needle="${f/private\/renet/\$SUBMODULE_PATH}"
        assert_contains "$body" "\"$needle\"" "BUILD_CONFIG_FILES must still declare $f"
        declared_count=$((declared_count + 1))
    done
    local actual
    actual="$(printf '%s\n' "$body" | grep -c '^        "')"
    assert_eq "$actual" "$declared_count" \
        "BUILD_CONFIG_FILES has $actual entries but this test knows about $declared_count; add the new one here"
    log_pass "the $declared_count declared inputs match BUILD_CONFIG_FILES exactly"
}

test_tag_is_deterministic() {
    # Baseline. Without it, "the tag changed" below proves nothing: it could
    # change on every invocation.
    build_fixture_tree
    local a b
    a="$(tag)"
    b="$(tag)"
    assert_eq "$a" "$b" "two runs over an unchanged tree must produce the same tag"
    assert_contains "$a" "-" "the tag must carry both halves (commit-confighash)"
    log_pass "the tag is deterministic over an unchanged tree ($a)"
}

test_every_declared_input_changes_the_tag() {
    # THE CONTROL PROOF, one per entry. An entry that does not move the tag is
    # decoration: it is in the list but not in the key, and a change to it would
    # reuse a stale image. This is the assertion that would have caught a path
    # pointed at the wrong build-renet.sh, because the wrong path cannot be
    # perturbed into changing anything.
    build_fixture_tree
    local base f after
    base="$(tag)"
    for f in "${DECLARED_INPUTS[@]}"; do
        printf 'perturbed %s\n' "$f" >"$ROOT/$f"
        after="$(tag)"
        if [[ "$after" == "$base" ]]; then
            log_fail "editing $f did not change the tag: it is declared but not hashed"
        fi
        # Restore so each input is proven independently rather than cumulatively.
        printf 'seed content for %s\n' "$f" >"$ROOT/$f"
        assert_eq "$(tag)" "$base" "restoring $f must return the tag to baseline"
    done
    log_pass "each of the ${#DECLARED_INPUTS[@]} declared inputs independently changes the tag"
}

test_infra_build_renet_is_not_an_input() {
    # The other direction, and the finding that prompted this file. Nine CI
    # steps run .ci/scripts/infra/build-renet.sh and it is NOT in the list --
    # correctly, because it compiles a dev binary for ct-tests / ci-ops-test,
    # which never pull the renet image and are never handed this tag. Pinning it
    # here means the next reader gets the answer instead of re-deriving it, and
    # a future decision to include it has to change this case deliberately.
    build_fixture_tree
    local base after
    base="$(tag)"
    printf 'perturbed infra\n' >"$ROOT/.ci/scripts/infra/build-renet.sh"
    after="$(tag)"
    assert_eq "$after" "$base" \
        "editing infra/build-renet.sh must NOT change the renet image tag (it does not affect the image)"
    log_pass "the sibling infra/build-renet.sh is deliberately outside the hash"
}

test_missing_input_fails_loudly() {
    # THE REGRESSION. Before the fix this exited 0 and printed a tag: a
    # DIFFERENT tag, because the remaining digests concatenate differently, so
    # the only symptom was a cache miss nobody would investigate.
    build_fixture_tree
    local base
    base="$(tag)"
    rm "$ROOT/.ci/scripts/build/build-renet.sh"
    run_tag
    assert_eq "$LAST_RC" "1" "a missing declared input must fail the script, not narrow the hash"
    assert_contains "$LAST_OUT" "Build-config input not found" "with a diagnostic that names the failure"
    assert_contains "$LAST_OUT" ".ci/scripts/build/build-renet.sh" "and names the missing path"
    log_pass "a missing declared input fails loudly instead of silently shrinking the key"
}

test_missing_input_does_not_emit_a_tag() {
    # The specific shape of the old bug: the caller
    # (initialize.sh:141, RENET_TAG=$(...)) captures stdout. Under the old
    # behaviour it captured a plausible-looking tag computed from a narrowed
    # key. Nothing may reach stdout on this path.
    build_fixture_tree
    rm "$ROOT/.ci/scripts/build/build-renet.sh"
    local stdout_only rc=0
    stdout_only="$(cd "$ROOT" && .ci/scripts/ci/generate-tag.sh --submodule private/renet 2>/dev/null)" || rc=$?
    assert_eq "$rc" "1" "the failure must be visible in the exit code the caller sees"
    assert_eq "$stdout_only" "" "no tag may be printed when an input is missing"
    log_pass "a missing input prints no tag, so a caller capturing stdout cannot use one"
}

test_every_declared_input_is_individually_load_bearing_for_the_failure() {
    # Sweep the class: the guard must cover every entry, not just the one that
    # prompted it. A guard that only checks the last element of a list is a
    # classic partial fix.
    build_fixture_tree
    local f
    for f in "${DECLARED_INPUTS[@]}"; do
        build_fixture_tree
        rm "$ROOT/$f"
        run_tag
        assert_eq "$LAST_RC" "1" "removing $f must fail the script"
        assert_contains "$LAST_OUT" "$f" "the diagnostic must name $f"
    done
    log_pass "all ${#DECLARED_INPUTS[@]} declared inputs are guarded, not just one"
}

test_other_modes_are_untouched() {
    # The guard lives in the --submodule branch. --self and the default
    # --self and the time-based mode must keep working even though initialize.sh
    # no longer uses --self for WEB_TAG (it moved to `--closure web` when D5
    # landed). Both modes are still reachable and still pinned here, because
    # nothing else guards them and a silent regression in either would only
    # surface as a mystery tag.
    build_fixture_tree
    local self_tag rc=0
    git -C "$ROOT" init -q .
    # The nested fixture submodule makes git warn about an embedded repo; it is
    # noise here, and the commit is only needed so --self has something to
    # rev-parse.
    git -C "$ROOT" add -A >/dev/null 2>&1
    git -C "$ROOT" -c user.email=fixture@example.com -c user.name=fixture commit -qm root >/dev/null 2>&1
    self_tag="$(cd "$ROOT" && .ci/scripts/ci/generate-tag.sh --self 2>/dev/null)" || rc=$?
    assert_eq "$rc" "0" "--self must still succeed"
    assert_eq "${#self_tag}" "7" "--self must still be a short commit hash"

    local time_tag
    time_tag="$(cd "$ROOT" && .ci/scripts/ci/generate-tag.sh 2>/dev/null)" || log_fail "default mode failed"
    if [[ ! "$time_tag" =~ ^[0-9]{8}-[0-9]{6}$ ]]; then
        log_fail "default mode must still emit YYYYMMDD-HHMMSS, got '$time_tag'"
    fi
    log_pass "--self and the default time-based mode are unaffected by the guard"
}

test_real_tree_still_produces_a_tag() {
    # The fixture proves the logic; this proves the guard is satisfiable by the
    # actual repo. If any declared path were wrong TODAY, this fails -- which is
    # the whole point of turning the silent skip into an error.
    local rc=0 out
    out="$(cd "$REPO_ROOT" && .ci/scripts/ci/generate-tag.sh --submodule private/renet 2>/dev/null)" || rc=$?
    assert_eq "$rc" "0" "the real tree must still generate a renet tag: $out"
    if [[ ! "$out" =~ ^[0-9a-f]+-[0-9a-f]{12}$ ]]; then
        log_fail "the real tag has an unexpected shape: '$out'"
    fi
    log_pass "the real private/renet tag still generates ($out)"
}

test_closure_tag_moves_when_the_released_version_moves() {
    # THE BUG THIS PINS, reproduced twice on real traffic before the fix.
    #
    # Both closure images BAKE a version in, and that version comes from the
    # latest git TAG -- not from a path -- so no CLOSURE_PATHS entry can cover
    # it. The OID-at-HEAD hashing is even documented as being "immune to the
    # in-job version bump", which is right for a dirty working file and exactly
    # wrong for this: the key went insensitive to the one input the image is
    # stamped with.
    #
    # Release v1.2.12 landed 2026-07-30T10:16:14Z mid-PR. Runs 30534726467 and
    # 30542942037 both failed `Validate Install Methods / Linux` with
    # "Version mismatch: expected '1.2.13', got '1.2.12'", because
    # `Build (Docker) / CLI Docker` was SKIPPED while its cached twin succeeded
    # and the mutable pr-546 tag kept serving a pre-release image. Deterministic
    # and self-perpetuating, not a race: nothing on the branch could move the key.
    #
    # Driven by swapping the RESOLVER rather than by cutting a git tag, so the
    # test needs no write access to the real tag namespace.
    #
    # IT DOES DISTURB A SHARED TREE, despite what this comment claimed until
    # 2026-08-17. It overwrites the REAL resolve-version.sh below and restores it
    # a second later, and generate-tag.sh gives it no fixture seam to do that in
    # (it is invoked via `cd "$REPO_ROOT"`). A gate reading a script in that
    # window sees a half-written file: this reddened gate-test:claude-hooks with
    # a bash syntax error in a file that parses clean and passes 884/0 serially.
    # The safety this comment asserted is why the test was classified T rather
    # than W. It is now in WRITER_TESTS in run-all.sh -- keep it there.
    local real="$REPO_ROOT/.ci/scripts/version/resolve-version.sh"
    local backup="$FIXTURE/resolve-version.real"
    mkdir -p "$FIXTURE"
    cp "$real" "$backup"

    local before after restored
    before="$(cd "$REPO_ROOT" && .ci/scripts/ci/generate-tag.sh --closure rdc --extra fixed 2>/dev/null)"
    printf '#!/bin/bash\n[ "$1" = "--current" ] && echo "v9.9.9" || echo "9.9.10"\n' >"$real"
    chmod +x "$real"
    after="$(cd "$REPO_ROOT" && .ci/scripts/ci/generate-tag.sh --closure rdc --extra fixed 2>/dev/null)"
    cp "$backup" "$real"
    restored="$(cd "$REPO_ROOT" && .ci/scripts/ci/generate-tag.sh --closure rdc --extra fixed 2>/dev/null)"

    if [[ "$before" == "$after" ]]; then
        log_fail "the rdc closure tag did NOT move when the released version moved ($before): a cached pre-release image would be served under the new version"
    fi
    # CONTROL: without this the assertion above is satisfied by ANY nondeterminism,
    # including a tag that changes on every invocation, which would be a different
    # and worse bug.
    assert_eq "$restored" "$before" \
        "restoring the resolver must reproduce the ORIGINAL tag, so the key is version-sensitive rather than merely unstable"
    log_pass "the closure tag tracks the released version ($before -> $after -> $restored)"
}

test_closure_tag_survives_an_unresolvable_version() {
    # This script also runs where no tag is reachable (a shallow clone, a fresh
    # fork). Failing to resolve must degrade to a well-defined key, never break
    # the build, so the marker is added even when empty.
    local real="$REPO_ROOT/.ci/scripts/version/resolve-version.sh"
    local backup="$FIXTURE/resolve-version.real2"
    mkdir -p "$FIXTURE"
    cp "$real" "$backup"
    printf '#!/bin/bash\nexit 1\n' >"$real"
    local out rc=0
    out="$(cd "$REPO_ROOT" && .ci/scripts/ci/generate-tag.sh --closure rdc --extra fixed 2>/dev/null)" || rc=$?
    cp "$backup" "$real"
    assert_eq "$rc" "0" "an unresolvable version must not fail tag generation"
    if [[ ! "$out" =~ ^rdc-[0-9a-f]{12}$ ]]; then
        log_fail "an unresolvable version produced a malformed tag: '$out'"
    fi
    log_pass "an unresolvable version degrades to a well-formed tag ($out)"
}

log_test "test-generate-tag-inputs"
test_declared_inputs_match_the_script
test_tag_is_deterministic
test_every_declared_input_changes_the_tag
test_infra_build_renet_is_not_an_input
test_missing_input_fails_loudly
test_missing_input_does_not_emit_a_tag
test_every_declared_input_is_individually_load_bearing_for_the_failure
test_other_modes_are_untouched
test_real_tree_still_produces_a_tag
test_closure_tag_moves_when_the_released_version_moves
test_closure_tag_survives_an_unresolvable_version
echo ""
log_pass "all tests passed"
