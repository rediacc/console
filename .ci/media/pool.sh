#!/bin/bash
# The render side of tutorial media: how many renders to run, how one render is run,
# and the streaming pool that keeps N of them in flight.
#
# These four belong together because they are the ONLY consumers of each other and
# because both `www tutorials media` and `www tutorials watch` drive them through the
# identical stdin contract ("tutorial<TAB>lang"). Splitting the pool from the sizing
# arithmetic is exactly how the two orchestrators would drift apart, which the comment
# on _tutorial_auto_jobs already warns about in its own words.
#
# Part of the media pipeline extraction (W10). Moved out of run.sh byte for byte in
# phase 1, comments included; phase 2 deleted run.sh's copy, and this module is the only
# definition of these four names anywhere.
# .ci/rediacc_ci/tests/gates/test_gate_media_pool.py asserts that ownership and exercises the pool
# with a fake renderer, so its concurrency bound, its per-item failure files and the
# caller's report block are all proved with node and npx absent. It is also where the one
# DELIBERATE behaviour change of phase 2 lives: `wait -n || true` in _tutorial_video_pool,
# explained where it sits.
#
# SOURCED, NEVER EXECUTED. Callers supply ROOT_DIR and the log_* helpers.

# Thin wrapper over the ONE readiness predicate. The bash enumeration this replaces
# duplicated the same query and had already drifted from it (it silently dropped the
# audio-directory precondition). Emitting "tutorial<TAB>lang" keeps the pool's stdin
# contract unchanged.
#
# Anything after the first two arguments is forwarded to the predicate verbatim, so the
# watch can ask the narrower question (--stale-only --require-provider voxcpm2) without a
# second copy of the invocation existing anywhere.
_tutorial_render_pairs() {
    local name="$1" lang="$2"
    shift 2
    local args=()
    [[ -n "$name" ]] && args+=(--cast "$name")
    [[ -n "$lang" ]] && args+=(--lang "$lang")
    node "$ROOT_DIR/packages/www/scripts/list-tutorial-render-pairs.js" "${args[@]}" "$@"
}

# Default render concurrency from the machine, not a constant. Renders are RAM-heavy
# (headless Chrome ~3 GB each) and must leave room for the narration process, which is
# ~11.8 GB RSS on its own, so both CPU and memory bound the answer.
#
# Shared by `media` and `watch` because both render WHILE narration holds the GPU and so
# face the identical constraint. A second copy of this arithmetic is exactly how the two
# would drift apart. Prints the number on stdout; every log_* line goes to stderr.
_tutorial_auto_jobs() {
    local cores mem_gb by_cpu by_mem jobs
    cores="$(media_cpu_count)"
    # A refusal from the memory seam means /proc/meminfo is unreadable, which on this
    # pipeline's only supported host means something is badly wrong. 0 GB drives the
    # arithmetic below to the floor of one render at a time, which is the safe answer:
    # over-scheduling here OOMs a card that is also holding an 11.8 GB narration.
    mem_gb="$(media_avail_mem_gb 2>/dev/null || echo 0)"
    by_cpu=$(((cores - 4) / 4))
    by_mem=$(((mem_gb - 16) / 4))
    jobs=$((by_cpu < by_mem ? by_cpu : by_mem))
    [[ "$jobs" -lt 1 ]] && jobs=1
    [[ "$jobs" -gt 6 ]] && jobs=6
    log_step "auto --jobs $jobs (${cores} cores, ${mem_gb} GB available)"
    echo "$jobs"
}

# Render exactly one (tutorial, lang) pair. Writes its OWN failure file rather than
# appending to a shared one, so nothing depends on single-line-append atomicity.
_tutorial_video_render_one() {
    local t="$1"
    local l="$2"
    local failure_file="$3"
    shift 3

    # Guards the language-independent browser-segments cache described above. With
    # lang-major emission this lock is essentially never contended; it exists so that a
    # hand-run invocation, or two orchestrator languages straddling a batch boundary,
    # cannot both record the same scene and copyFileSync over each other.
    local seg_lock="/tmp/rediacc-tut-seg.${t}.lock"

    log_step "  → $t × $l"
    (
        cd "$ROOT_DIR/packages/www" || exit 1
        # nice: renders must never starve the GPU job's own CPU work (the audio VAE, the
        # ffmpeg mastering chain, ASR). Narration is deliberately NOT niced.
        flock "$seg_lock" nice -n 10 \
            npx tsx scripts/generate-tutorial-video.ts --cast "$t" --lang "$l" "$@"
    ) || {
        log_error "  ✗ failed: $t × $l"
        echo "$t × $l" >"$failure_file"
        return 1
    }
}

# Bounded, STREAMING, globally-bounded render pool. Reads "tutorial<TAB>lang" lines from
# stdin and keeps at most $jobs renders in flight.
#
# It reads from a pipe rather than taking an array because that is what makes the
# orchestrator's overlap possible: work is dispatched as each line ARRIVES, so renders
# for a finished language start while the next language is still being narrated on the
# GPU. A per-language `( ... ) & wait` would instead force a barrier at every language
# boundary -- which either stalls the producer (starving the GPU, defeating the point) or
# multiplies concurrency to jobs×languages.
_tutorial_video_pool() {
    local jobs="$1"
    local failure_prefix="$2"
    shift 2
    local passthrough=("$@")

    local running=0
    local idx=0
    local t l
    while IFS=$'\t' read -r t l; do
        [[ -n "$t" && -n "$l" ]] || continue
        idx=$((idx + 1))
        _tutorial_video_render_one "$t" "$l" "${failure_prefix}.${idx}" "${passthrough[@]}" &
        running=$((running + 1))
        if [[ "$running" -ge "$jobs" ]]; then
            # `|| true` IS THE FIX, not a swallowed error. `wait -n` returns the REAPED
            # JOB'S exit status, and under `set -euo pipefail` -- which run.sh set, and
            # which .ci/scripts/lib/common.sh sets for this module -- a failed render
            # therefore killed the pool at its first reap. The damage was entirely in the
            # CALLER: every one of the three call sites
            # (www_tutorials_video, www_tutorials_media, www_tutorials_watch) reports
            # failures from an `if compgen -G "${failure_prefix}.*"` block placed AFTER
            # this function returns, so an abort here meant the "Failed tutorials:" list
            # was never printed and the per-pair files were abandoned in /tmp. Two of
            # those three call this bare, so the abort propagated out of them as well and
            # took the rest of their work with it.
            #
            # Reproduced 2026-09-06 with a renderer that exits 1: two pairs at --jobs 2
            # gave rc=1 and no report, while ONE pair at --jobs 2 -- too few to ever reach
            # this line -- gave rc=0 and a correct report. That asymmetry, a report that
            # appears only when the queue is shorter than the concurrency, is the
            # signature of this bug.
            #
            # Discarding the status loses nothing: _tutorial_video_render_one already
            # wrote "$failure_prefix.$idx" before it returned non-zero, so the failure is
            # recorded on disk. The file IS the channel; this return value never was.
            wait -n || true
            running=$((running - 1))
        fi
    done
    # Bare `wait` returns 0 in bash even when a reaped job failed (measured on 5.3.9), so
    # it needs no guard -- but that is a property of `wait`, not an intention, and it is
    # the reason the defect above only ever showed up past the concurrency bound.
    wait
    # EXPLICIT, because the last statement's status would otherwise be this function's.
    # The contract is "dispatch everything, record what failed"; failures travel in
    # $failure_prefix.* and the callers' compgen block is what turns them into an exit
    # code. Returning non-zero here would abort the very block that reports them.
    return 0
}
