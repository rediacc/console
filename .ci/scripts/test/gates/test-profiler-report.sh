#!/bin/bash
# Tests for the profiler's aggregation: .ci/scripts/ci/profiler/report.awk via
# .ci/scripts/ci/profiler/panel.sh.
#
# Driven entirely from SYNTHETIC sample files, so it needs no runner, no cgroup
# and no elapsed time. That is the point: the shapes worth testing are the ones
# a real run almost never produces on demand -- a sampler that died at sample
# two, a CPU series that is all zeros, a host leak, a 350-minute job.
#
# EVERY ANTI-VACUITY ASSERTION CARRIES ITS CONTROL. A checker that cannot fire
# is worth nothing, and a "the profile is clean" that is really "the checker is
# broken" is precisely the failure this tool exists to prevent, so each FAIL
# case is paired with the near-identical PASS case it was derived from.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

PANEL_SH="$SCRIPT_DIR/../../ci/profiler/panel.sh"
REPORT_AWK="$SCRIPT_DIR/../../ci/profiler/report.awk"
SAMPLER="$SCRIPT_DIR/../../ci/profiler/sampler-linux.sh"

[ -r "$PANEL_SH" ] || log_fail "panel.sh not found at $PANEL_SH"
[ -r "$REPORT_AWK" ] || log_fail "report.awk not found at $REPORT_AWK"

T0_MS=1700000000000
CEIL_CPU=1000
CEIL_MEM=$((5 * 1024 * 1024 * 1024))

# write_meta <file> [tier] [runner] [interval] [container_hint]
write_meta() {
    local f="$1" tier="${2:-CGROUP_V2}" runner="${3:-ubuntu-slim}" interval="${4:-10}"
    local hint="${5:-UNKNOWN}"
    printf '#META\t%s\t%s\t%s\t%s\t%s\t%s\tCGROUP_V2\tCGROUP_V2\t%s\n' \
        "$tier" "$CEIL_CPU" "$CEIL_MEM" "$interval" "$T0_MS" "$runner" "$hint" >"$f"
}

# write_samples <file> <count> <interval_s> <cpu_milli_base> <mem_base_mb> [mem_step_mb]
# Samples walk slightly so nothing is accidentally degenerate: a fixture that
# happens to be flat would make the degeneracy tests pass for the wrong reason.
write_samples() {
    local f="$1" count="$2" interval="$3" cpu="$4" memmb="$5" step="${6:-1}"
    local i t c m rx=0 tx=0
    for ((i = 1; i <= count; i++)); do
        t=$((T0_MS + i * interval * 1000))
        c=$((cpu + (i % 5) * 10))
        m=$(((memmb + (i * step) % 64) * 1048576))
        rx=$((rx + 100000))
        tx=$((tx + 50000))
        printf 'S\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$t" "$c" "$m" "$rx" "$tx" 8000000 900000 >>"$f"
    done
}

PANEL_OUT=""
PANEL_RC=0
# run_panel <sample-file> <wall_s> <strict>
run_panel() {
    local f="$1" wall="$2" strict="${3:-false}"
    PANEL_RC=0
    PANEL_OUT="$(PROFILER_SAMPLE_FILE="$f" PROFILER_WALL_S="$wall" PROFILER_STRICT="$strict" \
        PROFILER_TITLE="fixture-job" bash "$PANEL_SH" 2>&1)" || PANEL_RC=$?
}

test_normal_profile_renders() {
    local d="$1"
    local f="$d/s.tsv"
    write_meta "$f"
    write_samples "$f" 37 10 420 1200
    run_panel "$f" 370 true
    assert_exit_code 0 "$PANEL_RC" "a healthy profile must pass even under strict (output: $PANEL_OUT)"
    assert_contains "$PANEL_OUT" "## Runner Profile: fixture-job" "panel carries the job title"
    assert_contains "$PANEL_OUT" "**Runner:** ubuntu-slim (tier CGROUP_V2" "panel names runner and tier"
    assert_contains "$PANEL_OUT" "| Minute | CPU mean |" "per-minute table is rendered"
    assert_contains "$PANEL_OUT" "**CPU:** mean" "summary block present"
    assert_contains "$PANEL_OUT" "p95" "p95 is reported, not just mean and peak"
    assert_contains "$PANEL_OUT" "**Advisory:**" "an advisory is emitted"
    assert_not_contains "$PANEL_OUT" "::warning::" "a clean profile must not warn"
    log_pass "a normal profile renders table, summary, p95 and advisory with no findings"
}

test_per_minute_rows_are_per_minute() {
    # Shape check: 37 samples at 10s is ~6 minutes, so there must be 6-7 rows,
    # not 1 and not 37. A bucketer that collapsed everything into one row would
    # still "render a table" and pass a substring assertion.
    local d="$1"
    local f="$d/s.tsv" rows
    write_meta "$f"
    write_samples "$f" 37 10 420 1200
    run_panel "$f" 370
    rows="$(printf '%s\n' "$PANEL_OUT" | grep -c '^| [0-9][0-9]-' || true)"
    [ "$rows" -ge 6 ] && [ "$rows" -le 7 ] ||
        log_fail "expected 6-7 per-minute rows for a 370s profile, got $rows"
    log_pass "37 samples over ~6 minutes produce $rows one-minute rows"
}

test_short_sample_file_fails_the_floor() {
    local d="$1"
    local f="$d/s.tsv"
    write_meta "$f"
    write_samples "$f" 2 10 420 1200
    run_panel "$f" 370 true
    assert_exit_code 1 "$PANEL_RC" "2 samples over 370s must fail the floor under strict"
    assert_contains "$PANEL_OUT" "sample floor" "names the floor it broke"
    log_pass "a too-short sample file fails the anti-vacuity floor"
}

test_starved_sampler_fails_the_ratio() {
    # Above the hard floor of 3, below 0.8x expected: the sampler ran but was
    # starved or died mid-job. CONTROL: the same count with a matching wall
    # clock passes, so the failure is the RATIO and not the count.
    local d="$1"
    local f="$d/s.tsv" g="$d/ok.tsv"
    write_meta "$f"
    write_samples "$f" 10 10 420 1200
    run_panel "$f" 600 true
    assert_exit_code 1 "$PANEL_RC" "10 samples over a 600s job must fail 0.8x of 61 expected"
    assert_contains "$PANEL_OUT" "died early" "explains the sampler was starved or died"

    write_meta "$g"
    write_samples "$g" 10 10 420 1200
    run_panel "$g" 100 true
    assert_exit_code 0 "$PANEL_RC" "CONTROL: 10 samples over 100s is the expected count (output: $PANEL_OUT)"
    log_pass "the 0.8x ratio fires on a starved sampler and stays silent on a short job"
}

test_all_zero_cpu_fails() {
    local d="$1"
    local f="$d/s.tsv" g="$d/ok.tsv" i t
    write_meta "$f"
    for ((i = 1; i <= 30; i++)); do
        t=$((T0_MS + i * 10000))
        printf 'S\t%s\t0\t%s\t0\t0\t8000000\t900000\n' "$t" "$((1200 * 1048576 + i * 1048576))" >>"$f"
    done
    run_panel "$f" 300 true
    assert_exit_code 1 "$PANEL_RC" "an all-zero CPU series must fail"
    assert_contains "$PANEL_OUT" "degenerate CPU series" "names the degenerate series"

    # CONTROL: one single non-zero CPU sample in an otherwise identical file
    # must pass. Without this, a checker that failed EVERYTHING would look right.
    write_meta "$g"
    for ((i = 1; i <= 30; i++)); do
        t=$((T0_MS + i * 10000))
        printf 'S\t%s\t%s\t%s\t0\t0\t8000000\t900000\n' "$t" "$((i == 7 ? 30 : 0))" \
            "$((1200 * 1048576 + i * 1048576))" >>"$g"
    done
    run_panel "$g" 300 true
    assert_exit_code 0 "$PANEL_RC" "CONTROL: one non-zero CPU sample is a real (idle) profile (output: $PANEL_OUT)"
    log_pass "all-zero CPU fails; a single non-zero reading passes"
}

test_flat_ram_fails() {
    local d="$1"
    local f="$d/s.tsv" g="$d/ok.tsv" i t
    write_meta "$f"
    for ((i = 1; i <= 30; i++)); do
        t=$((T0_MS + i * 10000))
        printf 'S\t%s\t%s\t1258291200\t0\t0\t8000000\t900000\n' "$t" "$((400 + i))" >>"$f"
    done
    run_panel "$f" 300 true
    assert_exit_code 1 "$PANEL_RC" "an identical-RAM series must fail"
    assert_contains "$PANEL_OUT" "degenerate RAM series" "names the constant RAM series"

    # CONTROL: move exactly one byte of one sample. Real memory never repeats
    # byte-for-byte across 30 readings; a constant means a constant was recorded.
    write_meta "$g"
    for ((i = 1; i <= 30; i++)); do
        t=$((T0_MS + i * 10000))
        printf 'S\t%s\t%s\t%s\t0\t0\t8000000\t900000\n' "$t" "$((400 + i))" \
            "$((i == 9 ? 1258291201 : 1258291200))" >>"$g"
    done
    run_panel "$g" 300 true
    assert_exit_code 0 "$PANEL_RC" "CONTROL: a one-byte difference is a measurement (output: $PANEL_OUT)"
    log_pass "identical RAM across every sample fails; a one-byte difference passes"
}

test_host_leak_fails() {
    local d="$1"
    local f="$d/s.tsv"
    write_meta "$f" HOST_LEAK
    run_panel "$f" 300 true
    assert_exit_code 1 "$PANEL_RC" "a HOST_LEAK meta line must fail"
    assert_contains "$PANEL_OUT" "HOST_LEAK" "names the leak"
    assert_not_contains "$PANEL_OUT" "**Advisory:** MOVE TO" "a leaked profile must never advise a move"
    log_pass "HOST_LEAK fails and suppresses the advisory"
}

test_proc_host_tier_advises_only_when_the_label_disambiguates() {
    # The direction that matters most, and the one easiest to get backwards.
    # PROC_HOST on a real VM is TRUSTWORTHY -- ubuntu-latest jobs own the whole
    # VM, so host-wide and job-wide are the same numbers -- and muting the
    # advisor there would silence it across the entire population this tool
    # exists to triage. It is only poisoned inside a container or when the label
    # is missing and a VM cannot be told from a container.
    local d="$1"
    local f="$d/vm.tsv" g="$d/unknown.tsv" h="$d/slim.tsv"

    write_meta "$f" PROC_HOST ubuntu-latest
    write_samples "$f" 37 10 420 1200
    run_panel "$f" 370 true
    assert_exit_code 0 "$PANEL_RC" "PROC_HOST on a VM is a valid profile (output: $PANEL_OUT)"
    assert_contains "$PANEL_OUT" "**Advisory:** MOVE TO ubuntu-slim" "advises on a VM's own /proc numbers"
    assert_contains "$PANEL_OUT" "full VM this job owns" "shows its reasoning for trusting /proc here"

    write_meta "$g" PROC_HOST unknown
    write_samples "$g" 37 10 420 1200
    run_panel "$g" 370 true
    assert_exit_code 0 "$PANEL_RC" "an unlabelled PROC_HOST profile still renders"
    assert_contains "$PANEL_OUT" "**Advisory:** none" "declines when a VM cannot be told from a container"
    assert_contains "$PANEL_OUT" "no runner label was passed" "names the missing input"

    write_meta "$h" PROC_HOST ubuntu-slim
    write_samples "$h" 37 10 420 1200
    run_panel "$h" 370 true
    assert_contains "$PANEL_OUT" "**Advisory:** none" "declines when /proc was read inside slim's container"
    log_pass "PROC_HOST advises on a labelled VM and declines on slim or an unknown label"
}

test_mislabelled_container_is_caught() {
    # The most dangerous shape of all, and the one a label-armed guard cannot
    # see: a slim job whose label WRONGLY says ubuntu-latest. HOST_LEAK is armed
    # off the label so it never fires, and before this check the report answered
    # with a confident "MOVE TO ubuntu-slim" plus an explicit claim that host
    # numbers were "valid because 'ubuntu-latest' is a full VM the job owns".
    # Missing labels go mute; wrong labels lie, which is strictly worse.
    local d="$1"
    local f="$d/mislabelled.tsv" g="$d/genuine-vm.tsv"

    CEIL_CPU=4000 CEIL_MEM=$((16 * 1024 * 1024 * 1024)) \
        write_meta "$f" PROC_HOST ubuntu-latest 10 CONTAINER
    write_samples "$f" 37 10 420 1200
    run_panel "$f" 370 true
    assert_exit_code 1 "$PANEL_RC" "a container wearing a VM label must be a finding"
    assert_contains "$PANEL_OUT" "MISLABEL SUSPECTED" "names the contradiction"
    assert_contains "$PANEL_OUT" "HOST_LEAK could not fire" "explains why the label-armed guard missed it"
    assert_contains "$PANEL_OUT" "**Advisory:** none" "refuses to size anything from host numbers"
    assert_not_contains "$PANEL_OUT" "MOVE TO ubuntu-slim" "must not recommend a move on host numbers"

    # CONTROL: byte-identical except the fingerprint says HOST. A genuine VM must
    # still get its advice, or the check would just be a blanket mute on
    # PROC_HOST and would have caught this case for the wrong reason.
    CEIL_CPU=4000 CEIL_MEM=$((16 * 1024 * 1024 * 1024)) \
        write_meta "$g" PROC_HOST ubuntu-latest 10 HOST
    write_samples "$g" 37 10 420 1200
    run_panel "$g" 370 true
    assert_exit_code 0 "$PANEL_RC" "CONTROL: a genuine VM is not a finding (output: $PANEL_OUT)"
    assert_contains "$PANEL_OUT" "**Advisory:** MOVE TO ubuntu-slim" "a real VM still gets sized"
    assert_not_contains "$PANEL_OUT" "MISLABEL" "no false alarm on a genuine VM"
    log_pass "a container wearing a VM label is caught; a genuine VM is unaffected"
}

test_advisory_states_its_assumption_not_a_fact() {
    # The caveat used to assert "valid because 'X' is a full VM the job owns" --
    # a claim whose only evidence was the label, i.e. the exact input that is
    # wrong in the case above. It must state the assumption instead.
    local d="$1"
    local f="$d/vm.tsv"
    write_meta "$f" PROC_HOST ubuntu-latest
    write_samples "$f" 37 10 420 1200
    run_panel "$f" 370 true
    assert_contains "$PANEL_OUT" "on the assumption that" "states the assumption"
    assert_not_contains "$PANEL_OUT" "valid because" "never asserts validity it cannot verify"
    log_pass "the PROC_HOST caveat states an assumption rather than asserting a fact"
}

test_unlabelled_cgroup_job_is_sized_by_its_ceiling() {
    # The label is only load-bearing when the cgroup read FAILED. When it
    # succeeded, the enforced quota IS the box: a composite wrapper that cannot
    # thread a per-job label still gets a correct verdict here. Without this, an
    # unlabelled job already ON slim was told to "MOVE TO ubuntu-slim".
    local d="$1"
    local f="$d/slimsized.tsv" g="$d/vmsized.tsv" h="$d/mislabelled.tsv"

    write_meta "$f" CGROUP_V2 unknown
    write_samples "$f" 37 10 420 1200
    run_panel "$f" 370 true
    assert_exit_code 0 "$PANEL_RC" "an unlabelled cgroup profile still renders (output: $PANEL_OUT)"
    assert_contains "$PANEL_OUT" "**Advisory:** slim fits" "a 1-core/5GB quota is recognised as slim without a label"
    assert_not_contains "$PANEL_OUT" "MOVE TO ubuntu-slim" "must not tell a slim job to move to slim"

    # A WRONG label must lose to the enforced quota exactly as a missing one
    # does. This was live: keying the ceiling evidence on `unlabelled` meant a
    # job under a kernel-enforced 1-core/5GB quota, labelled ubuntu-latest, was
    # told it was "on a 4-vCPU VM" and should move to slim -- where it already
    # was. A label is a claim; a quota is a fact.
    write_meta "$h" CGROUP_V2 ubuntu-latest 10 CONTAINER
    write_samples "$h" 37 10 420 1200
    run_panel "$h" 370 true
    assert_exit_code 0 "$PANEL_RC" "a mislabelled cgroup profile renders (output: $PANEL_OUT)"
    assert_contains "$PANEL_OUT" "**Advisory:** slim fits" "the enforced quota beats a label that claims otherwise"
    assert_not_contains "$PANEL_OUT" "MOVE TO ubuntu-slim" "must not tell a quota-confined job to move to slim"
    assert_not_contains "$PANEL_OUT" "4x the core-minutes" "must not claim a 4-vCPU VM for a 1-core quota"

    # CONTROL: same missing label, but a 4-core/16GB quota. The ceiling now says
    # this is NOT a slim box, so the advisor must recommend the move instead.
    # Proves the inference reads the ceiling and is not just keying on 'unknown'.
    CEIL_CPU=4000 CEIL_MEM=$((16 * 1024 * 1024 * 1024)) write_meta "$g" CGROUP_V2 unknown
    write_samples "$g" 37 10 420 1200
    run_panel "$g" 370 true
    assert_exit_code 0 "$PANEL_RC" "an unlabelled large-quota profile renders (output: $PANEL_OUT)"
    assert_contains "$PANEL_OUT" "**Advisory:** MOVE TO ubuntu-slim" "a 4-core quota that fits slim is told to move"
    log_pass "an unlabelled cgroup job is sized by its enforced quota, both directions"
}

test_long_job_buckets_to_five_minutes() {
    local d="$1"
    local f="$d/s.tsv" rows bytes
    write_meta "$f"
    # 350 minutes at one sample per 10s.
    write_samples "$f" 2100 10 300 900
    run_panel "$f" 21000 true
    assert_exit_code 0 "$PANEL_RC" "a long healthy profile must pass (output: ${PANEL_OUT:0:400})"
    assert_contains "$PANEL_OUT" "| Minutes | CPU mean |" "long jobs switch to a Minutes header"
    rows="$(printf '%s\n' "$PANEL_OUT" | grep -c '^| [0-9][0-9]*-' || true)"
    [ "$rows" -ge 69 ] && [ "$rows" -le 71 ] ||
        log_fail "expected ~70 five-minute rows for a 350-minute job, got $rows"
    assert_contains "$PANEL_OUT" "| 00-05 |" "first bucket spans five minutes"
    assert_contains "$PANEL_OUT" "| 345-350 |" "last bucket reaches minute 350"
    bytes="${#PANEL_OUT}"
    [ "$bytes" -lt 1048576 ] || log_fail "panel is $bytes bytes, over the 1 MiB step-summary limit"
    log_pass "a 350-minute job renders $rows five-minute rows in $bytes bytes"
}

test_step_shorter_than_interval_is_unsampled_not_zero() {
    # The single most dangerous rendering: a 4-second step at a 10s interval has
    # nothing to sample, and printing "0.00 cores" would read as "this job is
    # free" to anyone deciding where to put it.
    local d="$1"
    local f="$d/s.tsv"
    write_meta "$f"
    run_panel "$f" 4 true
    assert_exit_code 0 "$PANEL_RC" "an unsampleable step is not a finding (output: $PANEL_OUT)"
    assert_contains "$PANEL_OUT" "<interval, unsampled" "reports the unsampled state verbatim"
    assert_contains "$PANEL_OUT" "NOT" "spells out that this is unmeasured, not idle"
    assert_not_contains "$PANEL_OUT" "**CPU:** mean 0.00" "must never render a zero CPU summary"
    log_pass "a step shorter than the interval reports '<interval, unsampled', never 0"
}

test_missing_sample_file_says_so() {
    local d="$1"
    run_panel "$d/never-written.tsv" 300 false
    assert_exit_code 0 "$PANEL_RC" "a missing file warns in non-strict mode"
    assert_contains "$PANEL_OUT" "no sample file was produced" "panel says the profile is missing"
    assert_contains "$PANEL_OUT" "::warning::" "a missing profile is annotated"
    run_panel "$d/never-written.tsv" 300 true
    assert_exit_code 1 "$PANEL_RC" "CONTROL: strict turns the same missing file into a failure"
    log_pass "a missing sample file is reported as missing, and is fatal under strict"
}

test_strict_flag_is_the_only_difference() {
    # The strict input is the whole failure policy, so prove it flips BOTH ways
    # on one identical input. `continue-on-error` being banned is why this seam
    # exists at all.
    local d="$1"
    local f="$d/s.tsv"
    write_meta "$f"
    write_samples "$f" 2 10 420 1200
    run_panel "$f" 370 false
    assert_exit_code 0 "$PANEL_RC" "non-strict keeps a bad profile green"
    assert_contains "$PANEL_OUT" "::warning::profiler:" "non-strict warns"
    assert_contains "$PANEL_OUT" "## Runner Profile" "non-strict still writes the panel"
    run_panel "$f" 370 true
    assert_exit_code 1 "$PANEL_RC" "strict fails on the identical input"
    assert_contains "$PANEL_OUT" "::error::profiler:" "strict escalates the annotation"
    log_pass "strict flips exit code and annotation level on identical input"
}

test_sampler_rejects_host_leak() {
    # The sampler's own hard failure, driven through PROFILER_CGROUP_ROOT against
    # a fake cgroup tree: a slim label plus host-sized limits must EXIT, not warn.
    local d="$1"
    local out rc=0
    mkdir -p "$d/cg"
    echo "max 100000" >"$d/cg/cpu.max"
    echo "max" >"$d/cg/memory.max"
    printf 'usage_usec 100\n' >"$d/cg/cpu.stat"
    out="$(PROFILER_CGROUP_ROOT="$d/cg" PROFILER_RUNNER_LABEL=ubuntu-slim \
        bash "$SAMPLER" --out "$d/s.tsv" --interval 1 2>&1)" || rc=$?
    assert_exit_code 3 "$rc" "an unquota'd cgroup on a slim label must abort (output: $out)"
    assert_contains "$out" "HOST_LEAK" "names the failure mode"
    assert_contains "$out" "memory ceiling" "names the memory number"
    assert_contains "$out" "CPU quota" "names the cpu number"
    assert_contains "$(cat "$d/s.tsv")" "HOST_LEAK" "writes a HOST_LEAK meta line for the panel"

    # CONTROL: identical tree, non-slim label -> the leak check must not fire,
    # because a 4-core VM legitimately reports 4 cores.
    rc=0
    out="$(PROFILER_CGROUP_ROOT="$d/cg" PROFILER_RUNNER_LABEL=ubuntu-latest \
        PROFILER_MAX_SECONDS=1 timeout 20 bash "$SAMPLER" --out "$d/ok.tsv" --interval 1 2>&1)" || rc=$?
    assert_exit_code 0 "$rc" "CONTROL: the same limits on ubuntu-latest are not a leak (output: $out)"
    log_pass "the sampler aborts on HOST_LEAK under a slim label and runs normally otherwise"
}

test_sampler_produces_a_real_profile() {
    # End-to-end on THIS machine: prove the sampler writes a meta line and real,
    # varying samples that the aggregator accepts. Without this the whole suite
    # only proves the aggregator can read files this file wrote.
    local d="$1"
    local rc=0 lines
    PROFILER_RUNNER_LABEL=selftest PROFILER_MAX_SECONDS=6 timeout 40 \
        bash "$SAMPLER" --out "$d/s.tsv" --interval 1 >/dev/null 2>&1 || rc=$?
    assert_exit_code 0 "$rc" "the sampler must exit cleanly on this machine"
    lines="$(grep -c '^S' "$d/s.tsv" || true)"
    [ "$lines" -ge 4 ] || log_fail "expected at least 4 real samples in 6s at 1s, got $lines"
    assert_contains "$(head -1 "$d/s.tsv")" "#META" "first line is the meta record"
    # STRICT on purpose. A healthy 6-second capture must not trip the starvation
    # ratio: the first sample lands one interval IN, so a W-second run yields
    # int(W/interval) samples and not one more. The off-by-one version of that
    # arithmetic flagged this exact capture as "starved or died early", and a
    # false alarm is how an anti-vacuity check ends up switched off.
    run_panel "$d/s.tsv" 7 true
    assert_exit_code 0 "$PANEL_RC" "a healthy short capture must not trip the ratio (output: $PANEL_OUT)"
    assert_contains "$PANEL_OUT" "## Runner Profile" "a real capture renders a panel"
    assert_contains "$PANEL_OUT" "**Samples:** $lines" "the panel counts every sample it was given"
    assert_not_contains "$PANEL_OUT" "sample floor" "no starvation finding on a healthy capture"
    log_pass "a live 6-second capture produced $lines samples and rendered"
}

test_sampler_reads_a_real_containers_ceiling() {
    # THE PREMISE THE WHOLE ADVISOR RESTS ON, proven against a real kernel
    # rather than a fixture. Every other cgroup case in this file writes its
    # own /sys/fs/cgroup files, so together they only prove the sampler can
    # read files this file wrote. This one puts it inside a container the
    # kernel is actually enforcing.
    #
    # ubuntu-slim is 1 vCPU / 5 GB in an UNPRIVILEGED CONTAINER, so the limits
    # here are chosen to match it exactly. Measured on this machine
    # 2026-08-05, `docker run --memory=5g --cpus=1` reports:
    #     memory.max = 5368709120   (exactly 5 GiB, the enforced ceiling)
    #     cpu.max    = 100000 100000 (quota/period = 1.0 core)
    #     nproc      = 20            <- the HOST
    #     MemTotal   = 59646420 kB   <- the HOST, ~57 GiB
    # That 20-vs-1 and 57GiB-vs-5GiB gap IS the failure mode: a sampler
    # trusting nproc and /proc/meminfo would size a 1-core 5 GB container as a
    # 20-core 57 GB machine and advise from it with total confidence.
    local d="$1"

    # NATIVE BRANCH FIRST, and it matters more than the docker one. If THIS
    # environment is itself quota-constrained then it IS the container, and the
    # premise can be proven directly against the kernel that is enforcing it --
    # no docker, no network, no image pull.
    #
    # This exists because the docker branch is self-defeating in the success
    # case: ubuntu-slim has no docker, so the moment this suite moves to the
    # runner the whole project is aiming at, the strongest proof would silently
    # become a SKIP. On slim this branch takes over instead and gets STRONGER,
    # because slim is exactly the container whose ceiling we care about.
    local live_mem=""
    if [ -r /sys/fs/cgroup/memory.max ]; then
        read -r live_mem </sys/fs/cgroup/memory.max || live_mem=""
    fi
    case "$live_mem" in
        '' | max | *[!0-9]*) live_mem="" ;;
    esac
    if [ -n "$live_mem" ]; then
        local nmeta nceil ntier rc2=0
        PROFILER_RUNNER_LABEL=selftest PROFILER_MAX_SECONDS=3 timeout 40 \
            bash "$SAMPLER" --out "$d/native.tsv" --interval 1 >/dev/null 2>&1 || rc2=$?
        assert_exit_code 0 "$rc2" "the sampler must run cleanly in this constrained environment"
        nmeta="$(grep '^#META' "$d/native.tsv" || true)"
        [ -n "$nmeta" ] || log_fail "no #META line written in a constrained environment"
        ntier="$(printf '%s\n' "$nmeta" | cut -f2)"
        nceil="$(printf '%s\n' "$nmeta" | cut -f4)"
        case "$ntier" in
            CGROUP_V2 | CGROUP_V1) ;;
            *) log_fail "a quota is enforced here (memory.max=$live_mem) but the sampler resolved '$ntier'" ;;
        esac
        # The whole thesis in one assertion: when the kernel enforces a ceiling,
        # the sampler reports THAT and never the machine behind it.
        [ "$nceil" -eq "$live_mem" ] ||
            log_fail "sampler reported $nceil but the enforced ceiling is $live_mem (it read the host)"
        log_pass "in this live cgroup-constrained environment the sampler reports the enforced ceiling ($nceil bytes), not the host's"
        return 0
    fi

    if ! command -v docker >/dev/null 2>&1 || ! docker version >/dev/null 2>&1; then
        log_pass "SKIP: unconstrained environment and no docker, real-container ceiling unproven here"
        return 0
    fi
    local out rc=0
    out="$(timeout 180 docker run --rm --memory=5g --cpus=1 \
        -v "$(cd "$(dirname "$SAMPLER")" && pwd):/p:ro" -v "$d:/w" \
        --entrypoint sh alpine:latest -c \
        'apk add --no-cache bash coreutils >/dev/null 2>&1;
         PROFILER_RUNNER_LABEL=ubuntu-slim PROFILER_MAX_SECONDS=3 \
           bash /p/sampler-linux.sh --out /w/c.tsv --interval 1 2>&1;
         head -1 /w/c.tsv' 2>&1)" || rc=$?
    if [ "$rc" -ne 0 ]; then
        log_pass "SKIP: container run failed (rc=$rc), ceiling unproven here: ${out:0:120}"
        return 0
    fi
    # PARSE THE FIELDS, do not substring-match the line. The first version of
    # this check globbed for *"cores=20"* | *"cores=1[0-9]"* | *"cores=[3-9]"*,
    # which could never fire for two independent reasons: the brackets sit
    # inside quotes so they are literal text rather than character classes, and
    # the meta line is TSV that contains no "cores=" anywhere. Three dead arms
    # reading as a passing host-leak guard is precisely the vacuous green this
    # whole file exists to refuse.
    local meta cpu_ceil mem_ceil tier
    meta="$(printf '%s\n' "$out" | grep '^#META' || true)"
    [ -n "$meta" ] || log_fail "no #META line came back from the container: ${out:0:300}"
    tier="$(printf '%s\n' "$meta" | cut -f2)"
    cpu_ceil="$(printf '%s\n' "$meta" | cut -f3)"
    mem_ceil="$(printf '%s\n' "$meta" | cut -f4)"

    # A cgroup tier is required: PROC_HOST here would mean it fell back to the
    # very files that lie inside a container.
    case "$tier" in
        CGROUP_V2 | CGROUP_V1) ;;
        *) log_fail "expected a cgroup tier inside a real container, got '$tier' (meta: $meta)" ;;
    esac
    # Exactly one core and exactly 5 GiB are what docker was told to enforce.
    # Anything larger is the host leaking through: this machine has 20 cores and
    # ~57 GiB, so the two are never confusable.
    [ "$cpu_ceil" -ge 900 ] && [ "$cpu_ceil" -le 1100 ] ||
        log_fail "cpu ceiling $cpu_ceil millicores is not the container's 1000 (host would be 20000): $meta"
    [ "$mem_ceil" -eq 5368709120 ] ||
        log_fail "memory ceiling $mem_ceil is not the container's 5 GiB (host would be ~61e9): $meta"
    log_pass "inside a real 1-core/5GiB container the sampler reads the CONTAINER's ceiling ($cpu_ceil millicores / $mem_ceil bytes), not the host's"
}

log_test "test-profiler-report"
with_temp_dir test_normal_profile_renders
with_temp_dir test_per_minute_rows_are_per_minute
with_temp_dir test_short_sample_file_fails_the_floor
with_temp_dir test_starved_sampler_fails_the_ratio
with_temp_dir test_all_zero_cpu_fails
with_temp_dir test_flat_ram_fails
with_temp_dir test_host_leak_fails
with_temp_dir test_proc_host_tier_advises_only_when_the_label_disambiguates
with_temp_dir test_mislabelled_container_is_caught
with_temp_dir test_advisory_states_its_assumption_not_a_fact
with_temp_dir test_unlabelled_cgroup_job_is_sized_by_its_ceiling
with_temp_dir test_long_job_buckets_to_five_minutes
with_temp_dir test_step_shorter_than_interval_is_unsampled_not_zero
with_temp_dir test_missing_sample_file_says_so
with_temp_dir test_strict_flag_is_the_only_difference
with_temp_dir test_sampler_rejects_host_leak
with_temp_dir test_sampler_produces_a_real_profile
with_temp_dir test_sampler_reads_a_real_containers_ceiling
echo ""
log_pass "all tests passed"
