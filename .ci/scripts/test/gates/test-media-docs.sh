#!/bin/bash
# Tests that the media folder's own DOCUMENTATION stays true, and that its coverage probe
# stays honest.
#
# WHY DOCUMENTATION NEEDS A GATE HERE MORE THAN ANYWHERE ELSE IN THIS TREE. These files
# carry an unusual amount of prose, on purpose: the driver contract makes comment
# preservation an acceptance criterion for the whole transformation, because several of
# these paragraphs are the only surviving record of an incident. Prose that dense is prose
# that decays, and it decays in one specific way that a reader cannot catch -- a path that
# was true when it was written and is not true now. Phase 3 alone moved four files, and
# every comment naming .ci/docker/tts became a lie the moment it did.
#
# So the first assertion is mechanical and narrow: every .ci/ path any media file NAMES,
# in code or in a comment, must exist. Narrow because a wider version does not work, and
# the reasons are worth stating rather than rediscovering:
#
#   - `npx tsx scripts/generate-tutorial-video.ts` in pool.sh is relative to a cwd, not to
#     the repository root, and resolving it from the root reports a false finding.
#   - teaser.sh QUOTES an error message containing a path that deliberately does not
#     exist; the whole point of the comment is that the path was wrong.
#
# Both were measured on 2026-09-06 while writing this, and both are why the scan is limited
# to .ci/ paths: those are the ones a relocation inside this repository breaks, they are
# always root-relative, and nothing quotes one as an example of a mistake.
#
# THE SECOND SUBJECT IS THE COVERAGE PROBE, and specifically the claim its header makes.
# .ci/media/coverage.sh says it measures without perturbing, after a first design that did
# perturb -- it forced xtrace into every child shell and made eight of the ten media gate
# tests fail, then reported the resulting coverage as a fact. That claim is now asserted:
# one gate test is run twice, with tracing on and off, and its stdout must be identical
# byte for byte. And the probe is run for real, because a measuring instrument that has
# rotted into printing zeroes reports "no coverage" in exactly the same tone as a genuine
# finding.
#
# Nothing here needs docker, node, npm, nvcc, aws, ssh, a GPU or a network.

set -euo pipefail

# ONE LINE TO REACH THE PRELUDE, and the prelude does the rest: it assigns ROOT, sources
# test-helpers.sh, and carries the ownership assertions and the module sandbox.
# shellcheck source=../../../media/verify.sh
# BLOCKER: the media gate-test prelude, the extraction's completeness proof and the module sandbox
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../media" && pwd)/verify.sh"

COVERAGE="$ROOT/.ci/media/coverage.sh"

# EVERY FILE THIS FOLDER OWNS, including the two shims that live outside it. The shims are
# the files whose prose is most likely to go stale, because they exist only to describe a
# move, so leaving them out would exempt the highest-risk prose in the change.
media_owned_files() {
    printf '%s\n' \
        "$ROOT/media.sh" \
        "$ROOT/.ci/docker/run-in-tts.sh" \
        "$ROOT/.ci/scripts/deploy/upload-media-to-r2.sh"
    find "$ROOT/.ci/media" -type f -name '*.sh' | sort
}

# dangling_ci_paths <file>...
#
# Every `.ci/...` path a file names that does not exist, as `<file>: <path>`.
#
# GLOBS ARE NOT PATHS. `test-media-*.sh` appears in several headers as the NAME OF A SET,
# and a token containing `*` is dropped rather than resolved: the alternative is either a
# false finding on every one of them or an exception list that grows with the prose.
dangling_ci_paths() {
    local f tok
    for f in "$@"; do
        grep -oE '\.ci/[A-Za-z0-9._*/-]+' "$f" | sed 's/[.,;:)]*$//' | sort -u |
            while IFS= read -r tok; do
                case "$tok" in
                    *'*'*) continue ;;
                esac
                [ -e "$ROOT/$tok" ] || printf '%s: %s\n' "${f#"$ROOT/"}" "$tok"
            done
    done
}

test_every_ci_path_the_media_files_name_exists() {
    local files=() f found
    while IFS= read -r f; do files+=("$f"); done < <(media_owned_files)
    # ANTI-VACUITY FIRST. A scan over an empty file list finds nothing wrong, and would
    # keep on finding nothing wrong after this folder was renamed out from under it.
    [ "${#files[@]}" -ge 12 ] ||
        log_fail "the media file list collapsed to ${#files[@]} entries; the scan below would pass over almost nothing"
    found="$(dangling_ci_paths "${files[@]}")"
    [ -z "$found" ] || log_fail "media files name .ci paths that do not exist:
$found"
    log_pass "every .ci path named across the ${#files[@]} media files resolves to something that exists"
}

test_the_dangling_path_scan_can_fail() {
    # CONTROL, in both directions. The scan is a grep with a character class and a filter,
    # which is the shape that goes quiet without announcing it.
    local d="$1"
    printf '# see .ci/media/no-such-file.sh for details\n' >"$d/stale.sh"
    [ -n "$(dangling_ci_paths "$d/stale.sh")" ] ||
        log_fail "the scan did not notice a comment naming a .ci path that does not exist"

    printf '# see .ci/media/verify.sh for details\n' >"$d/fresh.sh"
    [ -z "$(dangling_ci_paths "$d/fresh.sh")" ] ||
        log_fail "the scan reported a finding for a .ci path that does exist, so it fires on everything"

    printf '# every .ci/scripts/test/gates/test-media-*.sh sources it\n' >"$d/globbed.sh"
    [ -z "$(dangling_ci_paths "$d/globbed.sh")" ] ||
        log_fail "the scan treated a glob as a path, which would make it impossible to name a set of files in a comment"
    log_pass "the dangling-path scan fires on a stale path, stays silent on a live one, and ignores a glob"
}

# ---------------------------------------------------------------------------
# The coverage probe
# ---------------------------------------------------------------------------

test_the_coverage_probe_still_measures_something() {
    local out
    # ONE fast test rather than all ten: this is a gate, and a full probe run drives the
    # whole media battery. What is under test is the instrument, not the number.
    out="$("$COVERAGE" --only r2 2>&1)" || log_fail "the coverage probe failed to run: $out"
    assert_contains "$out" "r2.sh" "the probe must report the module the measured test exercises"
    assert_contains "$out" "TOTAL" "the probe must print a total"

    # NON-VACUITY, which for a coverage tool is the whole risk. A probe whose trace parsing
    # has silently stopped matching reports every module at zero, and zero is also what a
    # genuinely untested module looks like, so the two are indistinguishable without this.
    local pct
    pct="$(printf '%s\n' "$out" | awk '$1 == "r2.sh" {gsub(/%/, "", $4); print $4}')"
    [ -n "$pct" ] || log_fail "the probe printed no percentage for r2.sh; its output format has changed"
    [ "$pct" -ge 50 ] ||
        log_fail "the probe measured r2.sh at ${pct}% while running r2's own gate test, which drives both of its functions -- the trace is not being parsed"
    log_pass "the coverage probe runs, reports r2.sh at ${pct}% from r2's own gate test, and prints a total"
}

test_the_coverage_seam_does_not_perturb_the_run() {
    # THE CLAIM COVERAGE.SH MAKES ABOUT ITSELF, asserted rather than believed. The first
    # design of this probe forced SHELLOPTS=xtrace into every child shell, and eight of the
    # ten media gate tests then failed, because media_run_module captures merged stdout and
    # stderr and the behaviour cases assert on that text. The seam version writes to its own
    # descriptor. If that ever stops being true, the probe goes back to measuring a suite it
    # has broken -- and reporting the broken suite's coverage as a number.
    local d="$1" rc_off=0 rc_on=0
    "$ROOT/.ci/scripts/test/gates/test-media-r2.sh" >"$d/off" 2>"$d/off.err" || rc_off=$?
    MEDIA_COVERAGE_FILE="$d/trace" "$ROOT/.ci/scripts/test/gates/test-media-r2.sh" >"$d/on" 2>"$d/on.err" || rc_on=$?

    assert_eq "$rc_on" "$rc_off" "tracing must not change whether a gate test passes"
    if ! diff -u "$d/off" "$d/on" >"$d/diff"; then
        log_fail "tracing changed what the gate test printed:
$(cat "$d/diff")"
    fi
    # And the trace must actually have been written, or the comparison above is between two
    # untraced runs and proves nothing at all.
    [ -s "$d/trace" ] ||
        log_fail "MEDIA_COVERAGE_FILE produced no trace, so the two runs compared above were identical for the wrong reason"
    log_pass "a gate test's exit status and its entire stdout are identical with the coverage seam on and off, and the seam did write a trace"
}

log_test "test-media-docs"
test_every_ci_path_the_media_files_name_exists
with_temp_dir test_the_dangling_path_scan_can_fail
test_the_coverage_probe_still_measures_something
with_temp_dir test_the_coverage_seam_does_not_perturb_the_run
echo ""
log_pass "all tests passed"
