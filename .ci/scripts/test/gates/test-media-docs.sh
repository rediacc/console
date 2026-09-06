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
# finding. Since 2026-09-06 the probe also answers the question a percentage cannot -- which
# modules NO test drives at all -- and that answer is asserted here in both directions,
# because the real folder is clean and a clean folder is what a broken check also reports.
#
# THE THIRD SUBJECT IS .ci/docs/r2-media-setup.md. It is the only prose in this change that
# a reader reaches for BEFORE touching the pipeline, and four of its claims were false when
# measured on 2026-09-06. The section below the coverage cases says which four and which two
# are now mechanically enforced.
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
        "$ROOT/.ci/scripts/deploy/upload-media-to-r2.sh" \
        "$ROOT/.ci/docs/r2-media-setup.md"
    find "$ROOT/.ci/media" -type f -name '*.sh' | sort
}

# dangling_ci_paths <file>...
#
# Every `.ci/...` path a file names that does not exist, as `<file>: <path>`.
#
# GLOBS ARE NOT PATHS. `test-media-*.sh` appears in several headers as the NAME OF A SET,
# and a token containing `*` is dropped rather than resolved: the alternative is either a
# false finding on every one of them or an exception list that grows with the prose.
#
# `|| true` ON THE GREP, and it is not defensive noise: without it this gate DIED SILENTLY.
# A file that names no `.ci/` path at all makes grep exit 1, `set -o pipefail` carries that
# out of the pipeline, and `set -e` then kills the command substitution in the caller --
# producing exit 1, an empty stderr, and a single "TEST:" line with no finding named.
# Measured 2026-09-06 by planting one module with no `.ci` reference in it: the gate went
# red and said nothing whatsoever about why, which is worse than either verdict. Every
# module here happens to name a `.ci` path today, so this was one ordinary new file away
# from becoming somebody's afternoon.
dangling_ci_paths() {
    local f tok
    for f in "$@"; do
        { grep -oE '\.ci/[A-Za-z0-9._*/-]+' "$f" || true; } | sed 's/[.,;:)]*$//' | sort -u |
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

    # A FILE THAT NAMES NO .ci PATH AT ALL. This is the case that killed the gate silently
    # before the `|| true` above: grep exits 1, pipefail propagates it, set -e ends the
    # script mid-assertion, and the operator sees exit 1 with an empty stderr. Asserting
    # that the scan RETURNS here is what keeps that fix from being quietly undone.
    local rc=0
    printf 'zzz_no_paths_here() { :; }\n' >"$d/nopaths.sh"
    dangling_ci_paths "$d/nopaths.sh" >/dev/null || rc=$?
    assert_exit_code 0 "$rc" "a file naming no .ci path must leave the scan alive, not end the gate with an empty message"
    log_pass "the dangling-path scan fires on a stale path, stays silent on a live one, ignores a glob, and survives a file with no .ci path at all"
}

# ---------------------------------------------------------------------------
# The coverage probe
# ---------------------------------------------------------------------------

test_the_coverage_probe_still_measures_something() {
    local out
    # ONE fast test rather than the whole set: this is a gate, and a full probe run drives
    # every media gate test. What is under test is the instrument, not the number.
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

# ---------------------------------------------------------------------------
# THE THIRD SUBJECT: .ci/docs/r2-media-setup.md, whose claims about this tree were
# measured on 2026-09-06 and were wrong in four separate places.
#
# The four are the same decay in four costumes, and two of them get a mechanical
# assertion below rather than a one-time correction:
#
#   1. It said the R2 media credentials were "not yet wired into any workflow". They are:
#      ci-quality.yml fetches all three from Bitwarden and restores the tutorial-narration
#      audio cache with them, which is what stops validate:tutorial-audio from silently
#      skipping its central assertion.
#   2. It sent a reader to run.sh for www_tutorial_audio_restore. W10 moved that function
#      to .ci/media/r2.sh, so the reader finds nothing at all.
#      -> test_the_r2_doc_names_the_file_that_defines_each_media_function_it_names
#   3. It cited commit 8a537a367 for a deletion. The 2026-08-23 history rewrite changed
#      every SHA in this repository, and that object is now an ancestor of nothing and on
#      no branch, while still RESOLVING in any clone old enough to hold it, which is what
#      made the citation read as precise.
#      -> test_every_commit_the_r2_doc_cites_is_in_this_history
#   4. It counted "11" deep checkouts paired one-for-one with blob:none. Measured on
#      2026-09-06: 14, still paired. The pairing was the durable claim and the count was
#      not, so the count is GONE rather than corrected. A corrected count is the same
#      defect with a later date on it.
#
# 1 and 4 get no assertion because neither has a mechanical form worth its false
# positives; both are stated in the doc with the command that re-derives them.
# ---------------------------------------------------------------------------

R2_DOC="$ROOT/.ci/docs/r2-media-setup.md"

# doc_media_functions <doc> -- every shell function DEFINED in .ci/media that <doc> names
# inside backticks. Derived from BOTH sides, so a renamed function drops out of the set
# instead of becoming a stale exception nobody removes.
doc_media_functions() {
    local doc="$1" defined tokens
    defined="$({ grep -hoE '^[a-z_][a-z0-9_]*\(\)' "$ROOT"/.ci/media/*.sh || true; } |
        sed 's/()//' | sort -u)"
    tokens="$({ grep -oE '`[A-Za-z_][A-Za-z0-9_]*`' "$doc" || true; } | tr -d '`' | sort -u)"
    comm -12 <(printf '%s\n' "$defined") <(printf '%s\n' "$tokens")
}

# misplaced_function_homes <doc> -- every function above whose defining file the doc does
# NOT also name. Empty output is the invariant holding.
misplaced_function_homes() {
    local doc="$1" fn home
    while IFS= read -r fn; do
        [ -n "$fn" ] || continue
        while IFS= read -r home; do
            [ -n "$home" ] || continue
            grep -qF ".ci/media/$(basename "$home")" "$doc" ||
                printf '%s: defined in .ci/media/%s, which this document never names\n' \
                    "$fn" "$(basename "$home")"
        done < <({ grep -lE "^${fn}\(\)" "$ROOT"/.ci/media/*.sh || true; })
    done < <(doc_media_functions "$doc")
}

test_the_r2_doc_names_the_file_that_defines_each_media_function_it_names() {
    local fns found n
    fns="$(doc_media_functions "$R2_DOC")"
    n="$(printf '%s\n' "$fns" | { grep -c . || true; })"
    # ANTI-VACUITY. If the doc stops naming any media function, or the extraction of
    # function names stops matching, the loop below runs zero times and reports a clean
    # invariant it never tested.
    [ "$n" -ge 3 ] ||
        log_fail "only $n .ci/media function(s) are named in the R2 doc; the homing check below would assert almost nothing"
    found="$(misplaced_function_homes "$R2_DOC")"
    [ -z "$found" ] || log_fail "the R2 media doc names functions without naming the file that defines them:
$found"
    log_pass "all $n .ci/media functions the R2 doc names are accompanied by the module that defines them"
}

test_the_function_home_scan_can_fail() {
    # CONTROL, both directions, against fixture docs rather than the real one. run.sh is
    # the exact wrong home this check was written for, so it is the one planted.
    local d="$1"
    printf '`www_tutorial_audio_restore` lives in `run.sh`\n' >"$d/wrong.md"
    [ -n "$(misplaced_function_homes "$d/wrong.md")" ] ||
        log_fail "the scan accepted a doc that homes www_tutorial_audio_restore in run.sh, which is the defect it exists for"

    printf '`www_tutorial_audio_restore` lives in `.ci/media/r2.sh`\n' >"$d/right.md"
    [ -z "$(misplaced_function_homes "$d/right.md")" ] ||
        log_fail "the scan reported a finding for a doc that names the correct module, so it fires on everything:
$(misplaced_function_homes "$d/right.md")"
    log_pass "the function-home scan catches a function homed in the wrong file and stays silent on the right one"
}

# ---------------------------------------------------------------------------
# Commit citations
# ---------------------------------------------------------------------------

# doc_commit_tokens <doc> -- every BACKTICKED 7-to-12 hex token.
#
# The length ceiling is what keeps the Cloudflare zone id (32 hex, and backticked) out of
# the set, and the backticks are what let the doc discuss a SHA the rewrite killed: the
# dead 8a537a367 appears in that file WITHOUT backticks precisely so this scan leaves it
# alone, and the doc states that convention where a reader will meet it.
doc_commit_tokens() {
    { grep -oE '`[0-9a-f]{7,12}`' "$1" || true; } | tr -d '`' | sort -u
}

# non_ancestor_commits <repo> <doc> -- every cited token that is not an ancestor of HEAD in
# <repo>. Unresolvable and merely-unreachable collapse into one finding on purpose: from a
# reader's seat, "git cannot show me this" and "git shows me something on no branch" are
# the same broken citation.
non_ancestor_commits() {
    local repo="$1" doc="$2" tok
    while IFS= read -r tok; do
        [ -n "$tok" ] || continue
        git -C "$repo" merge-base --is-ancestor "$tok" HEAD 2>/dev/null ||
            printf '%s\n' "$tok"
    done < <(doc_commit_tokens "$doc")
}

test_every_commit_the_r2_doc_cites_is_in_this_history() {
    local found n
    n="$(doc_commit_tokens "$R2_DOC" | { grep -c . || true; })"
    [ "$n" -ge 1 ] ||
        log_fail "no backticked commit citation found in the R2 doc; either it stopped citing one or the token pattern stopped matching, and this check would pass forever either way"

    # A SHALLOW CLONE CANNOT ANSWER THIS, and saying so beats both a silent skip and a red
    # that is about the checkout rather than the doc. CI's quality-security job checks out
    # with fetch-depth: 0 paired with filter: blob:none, so the assertion does run there.
    # The control below runs either way, so the checker is never left unproven.
    if [ "$(git -C "$ROOT" rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then
        log_info "this clone is shallow, so the $n commit citation(s) in the R2 doc cannot be checked for ancestry here"
        return 0
    fi

    found="$(non_ancestor_commits "$ROOT" "$R2_DOC")"
    [ -z "$found" ] || log_fail "the R2 media doc cites commit(s) that are not in this repository's history:
$found
A history rewrite invalidates every SHA. Re-derive the citation, or write it without backticks if the point is that it is dead."
    log_pass "all $n commit citation(s) in the R2 doc are ancestors of HEAD"
}

test_the_commit_citation_scan_can_fail() {
    # CONTROL, in a throwaway repository, because the real doc has exactly one correct
    # citation and a scan with nothing to find proves nothing. Two divergent branches give
    # a commit that RESOLVES and is not an ancestor, which is the exact shape 8a537a367
    # has and the shape a scan built on `git cat-file -e` alone would wave through.
    # TWO STATEMENTS, not `local d="$1" repo="$d/repo"`. Bash expands every assignment word
    # BEFORE the `local` builtin runs, so the second one reads `d` from the caller's scope
    # where it does not exist, and `set -u` kills the test with "d: unbound variable".
    local d="$1"
    local repo="$d/repo" live dead
    mkdir -p "$repo"
    git -C "$repo" init -q
    git -C "$repo" config user.email probe@example.com
    git -C "$repo" config user.name probe
    printf 'a\n' >"$repo/f"
    git -C "$repo" add f
    git -C "$repo" commit -qm base
    live="$(git -C "$repo" rev-parse --short=9 HEAD)"
    git -C "$repo" checkout -q -b sibling
    printf 'b\n' >"$repo/f"
    git -C "$repo" commit -qam sibling
    dead="$(git -C "$repo" rev-parse --short=9 HEAD)"
    git -C "$repo" checkout -q -
    # HEAD is back on the base commit, so $dead resolves and is not an ancestor of it.

    printf 'see `%s`\n' "$dead" >"$d/dead.md"
    assert_eq "$(non_ancestor_commits "$repo" "$d/dead.md")" "$dead" "a citation that resolves but sits on no ancestor path must be reported"

    printf 'see `%s`\n' "$live" >"$d/live.md"
    [ -z "$(non_ancestor_commits "$repo" "$d/live.md")" ] ||
        log_fail "the scan reported a citation that IS an ancestor of HEAD, so it fires on everything"

    printf 'see `deadbeefcafe`\n' >"$d/junk.md"
    [ -n "$(non_ancestor_commits "$repo" "$d/junk.md")" ] ||
        log_fail "the scan accepted a citation git cannot resolve at all"

    # AND THE LENGTH CEILING, which is why the zone id in the real doc is not a finding. A
    # 32-hex token is not a commit citation in this file's vocabulary.
    printf 'zone `9e802649c143c9cefd811d8fd671d31c`\n' >"$d/zone.md"
    [ -z "$(doc_commit_tokens "$d/zone.md")" ] ||
        log_fail "a 32-hex identifier was taken for a commit citation, which would make every zone and account id in this document a permanent finding"
    log_pass "the citation scan catches an unreachable SHA and an unresolvable one, accepts an ancestor, and ignores a 32-hex identifier"
}

# ---------------------------------------------------------------------------
# Modules with no test at all
# ---------------------------------------------------------------------------

test_no_media_module_is_without_a_test() {
    local out rc=0
    out="$("$COVERAGE" --modules-without-tests 2>&1)" || rc=$?
    [ "$rc" -eq 0 ] || log_fail "a .ci/media module has no gate test naming it:
$out"
    assert_contains "$out" "named in the code of at least one media gate test" "the probe must say what it checked"
    log_pass "every .ci/media module is named in the code of at least one media gate test"
}

test_the_untested_module_report_can_fail() {
    # CONTROL, in all three directions the report has. Without it the assertion above is a
    # command that printed a reassuring sentence, and a coverage tool whose corpus has
    # collapsed prints exactly that sentence.
    local d="$1" out rc
    mkdir -p "$d/mods" "$d/gates" "$d/empty"
    printf 'covered_fn() { :; }\n' >"$d/mods/covered.sh"
    printf 'lonely_fn() { :; }\n' >"$d/mods/lonely.sh"
    # lonely.sh is named ONLY in a comment, which must not count as a test.
    printf '#!/bin/bash\n# this header mentions lonely.sh in prose\nMODULE="$ROOT/.ci/media/covered.sh"\n' \
        >"$d/gates/test-media-fixture.sh"

    rc=0
    out="$(MEDIA_COVERAGE_MODULE_DIR="$d/mods" MEDIA_COVERAGE_GATES_DIR="$d/gates" \
        "$COVERAGE" --modules-without-tests 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "a module no test names must make the probe exit non-zero"
    assert_contains "$out" "lonely.sh" "the probe must NAME the untested module, not merely count it"
    assert_not_contains "$out" "covered.sh" "the probe must not report a module a test does name"

    # THE OTHER DIRECTION.
    printf '#!/bin/bash\nmedia_run_module "$1" "lonely.sh" "$2"\nMODULE="$ROOT/.ci/media/covered.sh"\n' \
        >"$d/gates/test-media-fixture.sh"
    rc=0
    out="$(MEDIA_COVERAGE_MODULE_DIR="$d/mods" MEDIA_COVERAGE_GATES_DIR="$d/gates" \
        "$COVERAGE" --modules-without-tests 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "with every module named in code the probe must pass: $out"

    # AND THE VACUOUS CORPUS, which is the failure this whole check guards against
    # elsewhere: an empty module list reports nothing wrong and looks identical to a folder
    # in which everything is tested.
    rc=0
    out="$(MEDIA_COVERAGE_MODULE_DIR="$d/empty" MEDIA_COVERAGE_GATES_DIR="$d/gates" \
        "$COVERAGE" --modules-without-tests 2>&1)" || rc=$?
    assert_exit_code 1 "$rc" "an empty module folder must be refused, not reported as clean"
    assert_contains "$out" "no subject modules" "the refusal must say the corpus was empty"
    log_pass "the untested-module report names a planted module, ignores a prose-only mention, passes when every module is named in code, and refuses an empty corpus"
}

log_test "test-media-docs"
test_every_ci_path_the_media_files_name_exists
with_temp_dir test_the_dangling_path_scan_can_fail
test_the_r2_doc_names_the_file_that_defines_each_media_function_it_names
with_temp_dir test_the_function_home_scan_can_fail
test_every_commit_the_r2_doc_cites_is_in_this_history
with_temp_dir test_the_commit_citation_scan_can_fail
test_no_media_module_is_without_a_test
with_temp_dir test_the_untested_module_report_can_fail
test_the_coverage_probe_still_measures_something
with_temp_dir test_the_coverage_seam_does_not_perturb_the_run
echo ""
log_pass "all tests passed"
