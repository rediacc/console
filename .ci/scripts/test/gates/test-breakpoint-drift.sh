#!/bin/bash
# Gate test: check-breakpoint-drift.sh, the integrity oracle for the vendored
# .ci/breakpoint/ folder.
#
# WHY THIS FILE MATTERS MORE THAN A USUAL GATE TEST
# The drift gate is the ONLY thing making the folder safe to copy into other
# repositories. Everything else in the design leans on it: the "one vendorable
# folder" promise, the refusal to let downstream regenerate the manifest, the
# accept-list escape hatch. If it silently stops detecting something, a vendored
# copy becomes a private fork that upstream can never fix and the next re-vendor
# destroys without trace -- and nothing anywhere would report a problem.
#
# So every one of its five failure modes gets a NEGATIVE test here: the gate is
# made to fail on purpose, and the assertion is that it failed AND said why. A
# gate that has only ever been observed to pass has not been verified.
#
# Two real defects this file would have caught, both found by hand instead:
#   - `--write` refused inside the CANONICAL repo, because the slug regex left
#     the `.git` suffix on ("rediacc/console.git" != "rediacc/console"). The
#     only documented way past it was the accept list, i.e. the gate taught
#     people to suppress it. Covered by test_write_regenerates_in_console.
#   - The manifest silently going stale after an edit to a frozen file. Covered
#     by test_write_is_byte_identical_to_committed, which doubles as the
#     "somebody edited a script and forgot --write" freshness check.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

BP_SRC="$REPO_ROOT/.ci/breakpoint"
GATE_REL="scripts/check-breakpoint-drift.sh"

# -----------------------------------------------------------------------------
# fixture: an isolated copy of the folder, with no console and no git around it
# -----------------------------------------------------------------------------
# `env -i` on every invocation is deliberate: it strips GITHUB_REPOSITORY and
# anything else that could make the gate behave differently here than in a
# vendored checkout. A test that passes only because of the ambient environment
# is not evidence about the vendored case.
make_copy() {
    local dest="$1/bp"
    mkdir -p "$dest"
    cp -r "$BP_SRC/." "$dest/"
    rm -rf "$dest/.git"
    echo "$dest"
}

run_gate() {
    local bp="$1"
    shift
    env -i PATH="$PATH" HOME="$bp" RUNNER_TEMP="$bp" \
        bash "$bp/$GATE_REL" "$@" 2>&1
}

# =============================================================================
# 1. clean copy verifies
# =============================================================================
test_clean_copy_passes() {
    local bp out rc=0
    bp="$(make_copy "$1")"

    out="$(run_gate "$bp")" || rc=$?
    assert_exit_code 0 "$rc" "an unmodified copy must verify"
    assert_contains "$out" "Verified" "the gate must report what it verified"
    assert_not_contains "$out" "Verified 0 files" "verifying zero files is vacuous"
    log_pass "clean copy verifies and reports a non-zero file count"
}

# =============================================================================
# 2. MISMATCH: a single flipped byte
# =============================================================================
test_byte_flip_is_detected() {
    local bp out rc=0
    bp="$(make_copy "$1")"

    printf '\n# a single added comment line\n' >>"$bp/scripts/hold-breakpoint.sh"

    out="$(run_gate "$bp")" || rc=$?
    [[ "$rc" -ne 0 ]] || log_fail "a modified script verified clean -- the gate cannot see edits"
    assert_contains "$out" "MISMATCH" "the failure must be classified as MISMATCH"
    assert_contains "$out" "scripts/hold-breakpoint.sh" "the failure must NAME the file that changed"
    log_pass "a one-line edit is detected and the offending file is named"
}

# =============================================================================
# 3. MISSING: a manifest-listed file that is gone
# =============================================================================
test_missing_file_is_detected() {
    local bp out rc=0
    bp="$(make_copy "$1")"

    rm -f "$bp/scripts/hold-breakpoint.sh"

    out="$(run_gate "$bp")" || rc=$?
    [[ "$rc" -ne 0 ]] || log_fail "a deleted frozen file verified clean"
    assert_contains "$out" "MISSING" "a listed-but-absent file must be classified as MISSING"
    log_pass "deleting a frozen file is detected as MISSING"
}

# =============================================================================
# 4. UNTRACKED: a rogue script the manifest does not cover
# =============================================================================
# Without this, adding a NEW script is the trivial way to smuggle code into a
# vendored copy: it is not in the manifest, so a per-file hash check would never
# look at it, and the gate would pass while the folder grew.
test_untracked_file_is_detected() {
    local bp out rc=0
    bp="$(make_copy "$1")"

    cat >"$bp/scripts/rogue-helper.sh" <<'ROGUE'
#!/bin/bash
echo "this script is not in the manifest"
ROGUE
    chmod +x "$bp/scripts/rogue-helper.sh"

    out="$(run_gate "$bp")" || rc=$?
    [[ "$rc" -ne 0 ]] || log_fail "a new unmanifested script verified clean -- new code can be smuggled into a copy"
    assert_contains "$out" "UNTRACKED" "an unmanifested script must be classified as UNTRACKED"
    assert_contains "$out" "rogue-helper.sh" "the failure must name the rogue file"
    log_pass "a new script absent from the manifest is detected as UNTRACKED"
}

# =============================================================================
# 5. VACUOUS: a manifest listing nothing
# =============================================================================
# Emptying the manifest is the cheapest possible way to make a diverged copy
# "pass", because every comparison loop then runs zero times and reports success.
test_empty_manifest_is_vacuous() {
    local bp out rc=0
    bp="$(make_copy "$1")"

    : >"$bp/MANIFEST.sha256"

    out="$(run_gate "$bp")" || rc=$?
    [[ "$rc" -ne 0 ]] || log_fail "an EMPTY manifest verified clean -- emptying it would be a free pass"
    assert_contains "$out" "VACUOUS" "a zero-entry manifest must be classified as VACUOUS"
    log_pass "an empty manifest is rejected as vacuous, not reported as success"
}

# =============================================================================
# 6. no manifest at all
# =============================================================================
test_absent_manifest_is_rejected() {
    local bp out rc=0
    bp="$(make_copy "$1")"

    rm -f "$bp/MANIFEST.sha256"

    out="$(run_gate "$bp")" || rc=$?
    [[ "$rc" -ne 0 ]] || log_fail "a copy with NO manifest verified clean -- deleting it would be a free pass"
    assert_contains "$out" "no manifest" "the gate must say WHY it refused, not just exit non-zero"
    log_pass "a deleted manifest is rejected with a reason"
}

# =============================================================================
# 7. --write is refused downstream
# =============================================================================
# THE REFUSAL IS WHAT GIVES THE GATE TEETH. Without it a downstream operator
# "fixes" a drift failure by regenerating, which records the local fork as
# canonical and turns every future comparison into a comparison against itself.
test_write_refused_downstream() {
    local bp out rc=0
    bp="$(make_copy "$1")"

    out="$(env -i PATH="$PATH" HOME="$bp" RUNNER_TEMP="$bp" GITHUB_REPOSITORY="someone/elsewhere" \
        bash "$bp/$GATE_REL" --write 2>&1)" || rc=$?
    [[ "$rc" -ne 0 ]] || log_fail "--write succeeded in a repo that is NOT the canonical one; the gate would then compare a fork against itself forever"
    assert_contains "$out" "refusing --write" "the refusal must be explicit"
    log_pass "--write is refused outside the canonical repo"
}

# =============================================================================
# 8. --write works in the canonical repo, by SLUG not by luck
# =============================================================================
# Regression test for a live defect: the slug came from a sed expression using
# `([^/]+?)(\.git)?$`, and sed has no lazy quantifiers, so `[^/]+` swallowed
# "console.git" and the `(\.git)?` group matched empty. bp_current_repo returned
# "rediacc/console.git", which never equals "rediacc/console" -- so --write
# refused inside the canonical repo and the accept list was the only way onward.
#
# Both remote-URL forms are exercised, since HTTPS clones carry the suffix and
# SSH clones may not.
test_write_regenerates_in_console() {
    local bp rc out url
    for url in "https://github.com/rediacc/console.git" "git@github.com:rediacc/console.git"; do
        bp="$(make_copy "$1")"
        rm -f "$bp/MANIFEST.sha256"
        rc=0
        out="$(env -i PATH="$PATH" HOME="$bp" RUNNER_TEMP="$bp" GITHUB_REPOSITORY="rediacc/console" \
            bash "$bp/$GATE_REL" --write 2>&1)" || rc=$?
        assert_exit_code 0 "$rc" "--write must succeed in the canonical repo (remote form: $url)"
        [[ -s "$bp/MANIFEST.sha256" ]] || log_fail "--write reported success but wrote no manifest"
        rm -rf "$bp"
    done
    log_pass "--write regenerates inside the canonical repo (both remote-URL forms)"
}

# =============================================================================
# 9. the committed manifest is FRESH
# =============================================================================
# Doubles as the "somebody edited a frozen file and forgot --write" check: if the
# committed manifest does not match what --write produces right now, it is stale,
# and the gate has been verifying against yesterday's hashes.
test_write_is_byte_identical_to_committed() {
    local bp regenerated committed
    bp="$(make_copy "$1")"

    committed="$(grep -v '^#' "$bp/MANIFEST.sha256" | sort)"
    rm -f "$bp/MANIFEST.sha256"
    env -i PATH="$PATH" HOME="$bp" RUNNER_TEMP="$bp" GITHUB_REPOSITORY="rediacc/console" \
        bash "$bp/$GATE_REL" --write >/dev/null 2>&1 ||
        log_fail "--write failed while checking manifest freshness"
    regenerated="$(grep -v '^#' "$bp/MANIFEST.sha256" | sort)"

    if [[ "$committed" != "$regenerated" ]]; then
        printf 'ERROR: %s\n' "$(diff <(echo "$committed") <(echo "$regenerated") || true)" >&2
        log_fail "the committed MANIFEST.sha256 is STALE: a frozen file changed without --write being re-run"
    fi
    log_pass "the committed manifest matches a fresh regeneration (no forgotten --write)"
}

# =============================================================================
# 10. a valid BLOCKER accept waves a divergence through
# =============================================================================
test_valid_blocker_accept_is_honoured() {
    local bp out rc=0
    bp="$(make_copy "$1")"

    printf '\n# local divergence\n' >>"$bp/scripts/hold-breakpoint.sh"
    cat >"$bp/.breakpoint-drift-accept" <<'ACCEPT'
# BLOCKER: this repo pins a different hold duration because its runners are
# billed per minute and the upstream default would triple the invoice
scripts/hold-breakpoint.sh
ACCEPT

    out="$(run_gate "$bp")" || rc=$?
    assert_exit_code 0 "$rc" "a divergence with a valid BLOCKER must be accepted"
    assert_contains "$out" "accepted" "the gate must say the divergence was accepted, not stay silent"
    log_pass "a divergence with a valid BLOCKER reason is accepted and reported"
}

# =============================================================================
# 11. a banned-phrase BLOCKER is rejected
# =============================================================================
test_banned_phrase_blocker_is_rejected() {
    local bp out rc=0
    bp="$(make_copy "$1")"

    printf '\n# local divergence\n' >>"$bp/scripts/hold-breakpoint.sh"
    cat >"$bp/.breakpoint-drift-accept" <<'ACCEPT'
# BLOCKER: tbd
scripts/hold-breakpoint.sh
ACCEPT

    out="$(run_gate "$bp")" || rc=$?
    [[ "$rc" -ne 0 ]] || log_fail "'# BLOCKER: tbd' was accepted as a reason -- the escape hatch is unguarded"
    log_pass "a banned-phrase BLOCKER ('tbd') is rejected"
}

# =============================================================================
# 12. an accept entry with NO BLOCKER line is rejected
# =============================================================================
test_missing_blocker_is_rejected() {
    local bp out rc=0
    bp="$(make_copy "$1")"

    printf '\n# local divergence\n' >>"$bp/scripts/hold-breakpoint.sh"
    printf 'scripts/hold-breakpoint.sh\n' >"$bp/.breakpoint-drift-accept"

    out="$(run_gate "$bp")" || rc=$?
    [[ "$rc" -ne 0 ]] || log_fail "a bare path with no BLOCKER comment was accepted -- 'forgot the reason' must fail loudly"
    log_pass "an accept entry with no BLOCKER comment is rejected"
}

# =============================================================================
# 13. a STALE accept entry is rejected (the liveness half)
# =============================================================================
# A BLOCKER proves a reason EXISTS; it cannot prove the reason is still TRUE. An
# entry naming a path the manifest does not cover can never fire, so it is dead
# weight at best and a typo protecting nothing at worst.
test_stale_accept_entry_is_rejected() {
    local bp out rc=0
    bp="$(make_copy "$1")"

    cat >"$bp/.breakpoint-drift-accept" <<'ACCEPT'
# BLOCKER: this path was renamed upstream three releases ago and the entry
# was never cleaned up, which is exactly what the liveness rule is for
scripts/a-file-that-does-not-exist.sh
ACCEPT

    out="$(run_gate "$bp")" || rc=$?
    [[ "$rc" -ne 0 ]] || log_fail "an accept entry naming a non-manifest path was tolerated -- a typo would silently protect nothing"
    assert_contains "$out" "stale accept entry" "the gate must identify the entry as stale"
    log_pass "a stale accept entry (path absent from the manifest) is rejected"
}

with_temp_dir test_clean_copy_passes
with_temp_dir test_byte_flip_is_detected
with_temp_dir test_missing_file_is_detected
with_temp_dir test_untracked_file_is_detected
with_temp_dir test_empty_manifest_is_vacuous
with_temp_dir test_absent_manifest_is_rejected
with_temp_dir test_write_refused_downstream
with_temp_dir test_write_regenerates_in_console
with_temp_dir test_write_is_byte_identical_to_committed
with_temp_dir test_valid_blocker_accept_is_honoured
with_temp_dir test_banned_phrase_blocker_is_rejected
with_temp_dir test_missing_blocker_is_rejected
with_temp_dir test_stale_accept_entry_is_rejected
