#!/bin/bash
# Tests for .ci/media/pool.sh -- the render side of tutorial media.
#
# WHAT IS ACTUALLY WORTH ASSERTING HERE. Three of these four functions carry a property
# that a reader cannot check by reading:
#
#   _tutorial_render_pairs forwards everything after its first two arguments to the
#   readiness predicate VERBATIM. That is the whole reason the watch can ask a narrower
#   question without a second copy of the invocation existing; a lost "$@" would be
#   invisible until a watch quietly rendered the wrong set.
#
#   _tutorial_auto_jobs prints its number on STDOUT while every log line goes to stderr.
#   The pool's stdin is a work queue, so one log line on the wrong stream becomes a bogus
#   render. The case below captures stdout alone and requires it to hold nothing but the
#   number.
#
#   _tutorial_video_pool keeps at most $jobs renders in flight while STREAMING. A pool
#   that waited for each batch would still render everything and still pass a
#   "did all the work happen" test, so concurrency is measured rather than assumed.
#
#   _tutorial_video_pool RETURNS 0 EVEN WHEN RENDERS FAIL, and that is a contract rather
#   than sloppiness: its three callers report failures from a `compgen -G` block placed
#   AFTER it returns, and two of them call it bare under `set -e`. Phase 1 found the
#   opposite behaviour and pinned it as a defect; phase 2 fixed it in pool.sh, and the
#   case below is now the regression test, with the caller's report block reproduced
#   verbatim so "the report is reached" is observed rather than inferred.
#
# All of it runs with node, npx and tsx absent: the renderer is a fake that records when
# it starts and stops, which is exactly the evidence the concurrency claim needs.

set -euo pipefail

# ONE LINE TO REACH THE PRELUDE, and the prelude does the rest: it assigns ROOT, sources
# test-helpers.sh, and carries the ownership assertions and the module sandbox. This block
# used to be five lines whose only job was to find that file, in seven files;
# check:ci-shape-duplication counted them and it was right to.
# shellcheck source=../../../media/verify.sh
# BLOCKER: the media gate-test prelude, the extraction's completeness proof and the module sandbox
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../media" && pwd)/verify.sh"

MODULE="$ROOT/.ci/media/pool.sh"

MOVED=(
    _tutorial_render_pairs
    _tutorial_auto_jobs
    _tutorial_video_render_one
    _tutorial_video_pool
)

run_pool() {
    media_run_module "$1" "pool.sh" "$2"
}

test_every_moved_function_is_solely_owned_by_this_module() {
    # WHAT THIS REPLACED. Until the cutover run.sh carried its own copy of all four, and
    # this compared the bodies byte for byte. run.sh has no copies now -- and this module
    # has DELIBERATELY diverged from what run.sh used to hold, because phase 2 fixed the
    # `wait -n` defect here -- so byte-identity is not merely unmeasurable, it is the
    # wrong question. What is asserted instead is that there is one definition of each
    # name, it is here, and media-entry.sh resolves to it.
    media_assert_module_owns pool.sh "${MOVED[@]}"
}

test_the_ownership_assertion_can_fail() {
    media_assert_ownership_control "$1" pool.sh _tutorial_video_pool
}

_case_render_pairs_forwards_extra_args() {
    local d="$1"
    run_pool "$d" "_tutorial_render_pairs installation en --stale-only --require-provider voxcpm2" ||
        log_fail "the predicate call failed (output: $LAST_OUT)"
    local call
    call="$(fake_bin_record node)"
    assert_contains "$call" "packages/www/scripts/list-tutorial-render-pairs.js" "calls the ONE readiness predicate"
    assert_contains "$call" "--cast installation" "the first argument becomes --cast"
    assert_contains "$call" "--lang en" "the second argument becomes --lang"
    assert_contains "$call" "--stale-only --require-provider voxcpm2" "everything after the first two is forwarded verbatim"
}

_case_render_pairs_omits_empty_selectors() {
    local d="$1"
    run_pool "$d" "_tutorial_render_pairs '' ''" || log_fail "the predicate call failed (output: $LAST_OUT)"
    local call
    call="$(fake_bin_record node)"
    assert_not_contains "$call" "--cast" "an empty name must not become an empty --cast"
    assert_not_contains "$call" "--lang" "an empty lang must not become an empty --lang"
}

test_render_pairs_is_a_thin_forwarder() {
    local d="$1"
    with_fake_bin "node +uname" _case_render_pairs_forwards_extra_args "$d"
    with_fake_bin "node +uname" _case_render_pairs_omits_empty_selectors "$d"
    log_pass "_tutorial_render_pairs forwards extra arguments verbatim and omits empty selectors"
}

# script_machine <cores> <gib-available>
#
# _tutorial_auto_jobs reads the machine through exactly two commands: `nproc`, and an
# `awk` over /proc/meminfo. /proc/meminfo cannot be staged, so awk is the injection
# point -- it is scripted to print the memory figure the case wants, which is precisely
# what the real one would have printed.
#
# BOTH NOW REACH THE MACHINE THROUGH .ci/media/portable.sh's seams (media_cpu_count and
# media_avail_mem_gb) rather than being spelled inline, and both fakes still work
# unchanged, which is the point: a seam that changed what the module observes would be a
# rewrite wearing a refactor's clothes. media_avail_mem_gb keeps the division INSIDE awk
# for exactly this reason -- the fake prints GiB, and a shell-side divide would turn that
# into 0.
script_machine() {
    printf '#!/bin/bash\necho %s\n' "$1" >"$FAKE_BIN_DIR/nproc"
    printf '#!/bin/bash\necho %s\n' "$2" >"$FAKE_BIN_DIR/awk"
    chmod +x "$FAKE_BIN_DIR/nproc" "$FAKE_BIN_DIR/awk"
}

_case_auto_jobs_arithmetic() {
    local d="$1" cores="$2" gib="$3" expect="$4"
    script_machine "$cores" "$gib"
    # STDOUT ONLY. The number is the return value; every log_* line is stderr. Redirecting
    # them apart is the assertion, not a convenience -- the pool reads this stream.
    "$BASH" -c "
        ROOT_DIR='$d'
        source '$ROOT/.ci/scripts/lib/common.sh'
        source '$ROOT/.ci/media/portable.sh'
        source '$MODULE'
        _tutorial_auto_jobs" >"$d/jobs" 2>"$d/log"
    assert_eq "$(<"$d/jobs")" "$expect" "jobs for ${cores} cores / ${gib} GiB"
    assert_contains "$(<"$d/log")" "auto --jobs" "the log line exists, and it is on STDERR"
}

test_auto_jobs_is_bounded_by_cpu_memory_and_a_ceiling() {
    local d="$1"
    # CPU-bound: (20-4)/4 = 4 against (64-16)/4 = 12.
    with_fake_bin "nproc awk +chmod +uname" _case_auto_jobs_arithmetic "$d" 20 64 4
    # Memory-bound: (64-4)/4 = 15 against (32-16)/4 = 4.
    with_fake_bin "nproc awk +chmod +uname" _case_auto_jobs_arithmetic "$d" 64 32 4
    # The ceiling: both arms exceed 6.
    with_fake_bin "nproc awk +chmod +uname" _case_auto_jobs_arithmetic "$d" 64 256 6
    # The floor: a small machine still gets one render rather than zero.
    with_fake_bin "nproc awk +chmod +uname" _case_auto_jobs_arithmetic "$d" 4 8 1
    log_pass "_tutorial_auto_jobs is bounded by CPU, by memory, by a ceiling of 6 and a floor of 1, and prints only the number on stdout"
}

# script_renderer <trace-file> [exit-code]
#
# flock and nice become transparent passthroughs -- the real ones would need a lock file
# and a priority change that prove nothing here -- and npx becomes the renderer, which
# records the moment it starts and the moment it stops. That trace is what makes the
# concurrency claim measurable instead of asserted.
script_renderer() {
    local trace="$1" code="${2:-0}"
    printf '#!/bin/bash\nshift\nexec "$@"\n' >"$FAKE_BIN_DIR/flock"
    printf '#!/bin/bash\nshift 2\nexec "$@"\n' >"$FAKE_BIN_DIR/nice"
    cat >"$FAKE_BIN_DIR/npx" <<NPX
#!/bin/bash
printf 'S\n' >>"$trace"
sleep 0.3
printf 'E\n' >>"$trace"
exit $code
NPX
    chmod +x "$FAKE_BIN_DIR/flock" "$FAKE_BIN_DIR/nice" "$FAKE_BIN_DIR/npx"
}

# max_overlap <trace-file>: the largest number of renders that were ever in flight.
max_overlap() {
    local line cur=0 max=0
    while read -r line; do
        [ "$line" = "S" ] && cur=$((cur + 1))
        [ "$line" = "E" ] && cur=$((cur - 1))
        [ "$cur" -gt "$max" ] && max="$cur"
    done <"$1"
    printf '%s' "$max"
}

_case_pool_bounds_concurrency() {
    local d="$1"
    script_renderer "$d/trace"
    : >"$d/trace"
    run_pool "$d" "
        printf 'a\ten\nb\ten\nc\ten\nd\ten\ne\ten\n' |
            _tutorial_video_pool 2 '$d/fail'" ||
        log_fail "the pool failed (output: $LAST_OUT)"
    local starts
    starts="$(grep -c '^S$' "$d/trace")"
    assert_eq "$starts" "5" "every queued pair must be rendered"
    assert_eq "$(max_overlap "$d/trace")" "2" "at most --jobs renders may be in flight at once"
    assert_eq "$(compgen -G "$d/fail.*" || true)" "" "a clean run leaves no failure files"
}

_case_a_lone_failure_is_recorded_and_reportable() {
    local d="$1"
    script_renderer "$d/trace2" 1
    : >"$d/trace2"
    local rc=0
    run_pool "$d" "
        printf 'a\ten\n' |
            _tutorial_video_pool 2 '$d/f2'" || rc=$?
    # FEWER ITEMS THAN --jobs, so the loop never reaches `wait -n`. The pool records the
    # failure and returns 0, which is what lets www_tutorials_video's `compgen -G` block
    # print the "Failed tutorials:" list.
    assert_exit_code 0 "$rc" "with fewer pairs than jobs the pool records and returns 0"
    local files
    files="$(compgen -G "$d/f2.*" | wc -l)"
    assert_eq "$files" "1" "each failed render writes its OWN file, so nothing depends on append atomicity"
    assert_contains "$(cat "$d"/f2.*)" "a × en" "the failure file names the pair"
}

# THE CALLER'S REPORT BLOCK, REPRODUCED VERBATIM. www_tutorials_video, _media and _watch
# all end the same way: run the pool, then `if compgen -G "${failure_prefix}.*"` to print
# the list and return 1. Two of the three call the pool BARE, so under `set -e` a non-zero
# return from it skips that block entirely. Running the pool alone therefore cannot tell
# the fixed behaviour from the broken one -- both end with failure files on disk and a
# non-zero somewhere -- which is why this reproduces the caller instead of the pool.
POOL_WITH_CALLER_REPORT='
    printf "a\ten\nb\tfr\n" | _tutorial_video_pool 2 "PREFIX"
    if compgen -G "PREFIX".* >/dev/null; then
        log_error "Failed tutorials:"
        cat "PREFIX".* >&2
        exit 1
    fi
    echo "NO-FAILURES-SEEN"'

_case_a_reaped_failure_still_reaches_the_report() {
    local d="$1"
    script_renderer "$d/trace3" 1
    : >"$d/trace3"
    local rc=0
    run_pool "$d" "${POOL_WITH_CALLER_REPORT//PREFIX/$d/f3}" || rc=$?

    # THE DEFECT THIS PINS, AND THE FIX THAT CLOSED IT. Once the queue reaches --jobs the
    # pool calls `wait -n`, which returns the REAPED JOB'S exit status. Under the
    # `set -euo pipefail` that run.sh and .ci/scripts/lib/common.sh both set, a non-zero
    # there aborted _tutorial_video_pool on the spot, so the block above never ran: the
    # "Failed tutorials:" list was never printed and the per-pair files were abandoned in
    # /tmp. Reproduced 2026-09-06 with a renderer that exits 1 -- two pairs at --jobs 2
    # gave rc=1 and NO report, one pair at --jobs 2 gave rc=0 and a correct report --
    # characterised here as a defect while both copies of the function still existed, and
    # fixed in .ci/media/pool.sh (`wait -n || true`, plus an explicit `return 0`) once
    # run.sh's copy was gone.
    #
    # rc is 1 either way, so IT IS NOT THE EVIDENCE. The report line is: before the fix
    # nothing printed it, and the sibling job was still in flight when the pool's shell
    # died, so its failure file was a race. After the fix both pairs are waited for and
    # both are listed.
    assert_exit_code 1 "$rc" "failures still make the CALLER exit 1 -- via its report block, not via the pool aborting"
    assert_contains "$LAST_OUT" "Failed tutorials:" "the report block must be REACHED; this line is the whole difference the fix makes"
    assert_contains "$LAST_OUT" "a × en" "the first pair is named in the report"
    assert_contains "$LAST_OUT" "b × fr" "and so is the pair that was in flight when the old code aborted"
    assert_not_contains "$LAST_OUT" "NO-FAILURES-SEEN" "the clean-run path must not be taken when renders failed"
    local files
    files="$(compgen -G "$d/f3.*" | wc -l)"
    assert_eq "$files" "2" "both failed pairs write their own file, and the pool now waits for both"
}

_case_restoring_the_defect_loses_the_report() {
    # CONTROL, and the red half of a red-then-green. A copy of pool.sh with `|| true` and
    # the explicit `return 0` taken back out -- which is exactly the pre-fix source -- must
    # make the case above fail. If the report still appeared, the assertion that carries
    # the fix would be proving nothing.
    local d="$1"
    local MEDIA_MODULE_DIR="$d/mutant"
    script_renderer "$d/trace4" 1
    : >"$d/trace4"
    local rc=0
    run_pool "$d" "${POOL_WITH_CALLER_REPORT//PREFIX/$d/f4}" || rc=$?
    assert_exit_code 1 "$rc" "the pre-fix pool still ends non-zero, which is why the exit code alone never showed the bug"
    assert_not_contains "$LAST_OUT" "Failed tutorials:" "with the defect restored the report block must NOT be reached"
    assert_not_contains "$LAST_OUT" "NO-FAILURES-SEEN" "and the clean-run path is not reached either -- the shell simply died"
}

test_the_pool_streams_within_its_bound_and_records_failures() {
    local d="$1"
    mkdir -p "$d/packages/www"
    with_fake_bin "flock nice npx +sleep +grep +chmod +cat +uname" _case_pool_bounds_concurrency "$d"
    with_fake_bin "flock nice npx +sleep +chmod +cat +wc +uname" _case_a_lone_failure_is_recorded_and_reportable "$d"
    with_fake_bin "flock nice npx +sleep +chmod +cat +wc +uname" _case_a_reaped_failure_still_reaches_the_report "$d"
    # The red half of the same claim, against a copy of the module with the fix undone.
    mkdir -p "$d/mutant"
    sed -e 's/^            wait -n || true$/            wait -n/' -e '/^    return 0$/d' "$MODULE" >"$d/mutant/pool.sh"
    grep -q '^            wait -n$' "$d/mutant/pool.sh" || log_fail "the fix was not undone in the mutant, so the control would pass for the wrong reason"
    grep -q '^    return 0$' "$d/mutant/pool.sh" && log_fail "the explicit return 0 survived in the mutant, so the control would pass for the wrong reason"
    with_fake_bin "flock nice npx +sleep +chmod +cat +wc +uname" _case_restoring_the_defect_loses_the_report "$d"
    log_pass "the pool keeps at most --jobs renders in flight, writes one failure file per failed pair, and lets the caller's report block run -- which the pre-fix source does not"
}

log_test "test-media-pool"
test_every_moved_function_is_solely_owned_by_this_module
with_temp_dir test_the_ownership_assertion_can_fail
with_temp_dir test_render_pairs_is_a_thin_forwarder
with_temp_dir test_auto_jobs_is_bounded_by_cpu_memory_and_a_ceiling
with_temp_dir test_the_pool_streams_within_its_bound_and_records_failures
echo ""
log_pass "all tests passed"
