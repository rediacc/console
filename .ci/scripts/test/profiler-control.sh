#!/bin/bash
# Drive a KNOWN workload past the sampler and check that the numbers come back.
#
# WHY: every other test in this tree feeds the aggregator synthetic samples, so
# nothing else proves that sampler-linux.sh reads the machine correctly. A
# sampler that returns plausible-looking garbage passes every unit test and then
# moves a job onto a runner that cannot hold it. This is the control: four
# phases whose answers are known before the run starts.
#
#   1. BUSY   30s of exactly one spinning core   expect +1.00 +/- 0.15 cores over idle
#   2. IDLE   30s of nothing                     expect mean < 0.25 cores
#   3. ALLOC  hold 512 MiB ANONYMOUS             expect a 400-640 MiB step
#   4. DISK   write then delete 1 GiB            expect ~1 GiB +/- 15%
#
# BUSY is a DELTA over IDLE rather than an absolute, and at PROC_HOST tier the
# three CPU/RAM phases are SKIPPED outright: without a cgroup the sampler reads
# the whole machine, so on a shared box those numbers measure everything else
# running there. A control that fails because the laptop was busy is testing the
# laptop -- and one that PASSES there would be worse, because it would certify
# the sampler on evidence it never had. That case exits 2, INCONCLUSIVE, which
# is neither green nor red. Disk keeps its verdict at every tier: `df` measures
# the filesystem, and a 1 GiB write dominates whatever else is happening.
#
# Measured 2026-08-05 on the dev box: the bash allocation in phase 3 is a real
# 515 MiB of anonymous RSS (VmRSS delta of the holding process), which is why
# the band is 400-640 and not something looser.
#
# The tolerances are wide ON PURPOSE. They are not measuring accuracy, they are
# distinguishing "reads the machine" from "returns a constant": a broken sampler
# fails all four, not one. Phase 3 allocates ANONYMOUS memory (bash heap), not
# page cache, because page cache does not move memory.current the way an OOM
# does -- the working-set figure this tool reports is deliberately
# memory.current minus inactive_file, and a 512 MiB file write would not shift
# it at all.
#
# Usage:
#   .ci/scripts/test/profiler-control.sh [--interval <sec>] [--keep]
#
# Optional env:
#   PROFILER_CONTROL_DIR   where the 1 GiB file is written (default the
#                          workspace, since that is the filesystem `df` watches)
#
# Exit: 0 every judged phase within tolerance, 1 any phase outside it,
#       2 setup error OR inconclusive (PROC_HOST tier, see below).

set -uo pipefail
export LC_ALL=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMPLER="$SCRIPT_DIR/../ci/profiler/sampler-linux.sh"

INTERVAL=2
KEEP=0
BUSY_S=30
IDLE_S=30
ALLOC_S=30
DISK_S=75 # long enough that a decimated `df` tick lands inside the phase

while (($# > 0)); do
    case "$1" in
        --interval)
            INTERVAL="${2:-2}"
            shift 2
            ;;
        --keep)
            KEEP=1
            shift
            ;;
        --help | -h)
            sed -n '2,30p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "profiler-control.sh: unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

[ -x "$SAMPLER" ] || [ -r "$SAMPLER" ] || {
    echo "profiler-control.sh: sampler not found at $SAMPLER" >&2
    exit 2
}

WORK="$(mktemp -d)" || exit 2
DATA_DIR="${PROFILER_CONTROL_DIR:-${GITHUB_WORKSPACE:-$WORK}}"
TSV="$WORK/samples.tsv"
MARKS="$WORK/phases.tsv"
BLOB="$DATA_DIR/.profiler-control-blob.$$"

SAMPLER_PID=""
BUSY_PID=""
cleanup() {
    [ -n "$BUSY_PID" ] && kill "$BUSY_PID" 2>/dev/null
    [ -n "$SAMPLER_PID" ] && kill "$SAMPLER_PID" 2>/dev/null
    rm -f "$BLOB"
    [ "$KEEP" = 1 ] || rm -rf "$WORK"
    [ "$KEEP" = 1 ] && echo "kept: $WORK"
    return 0
}
trap cleanup EXIT

now_ms() {
    local r sec frac
    r="$EPOCHREALTIME"
    sec="${r%.*}"
    frac="${r#*.}"
    if [ "$frac" = "$r" ]; then
        NOW_MS=$((sec * 1000))
    else
        NOW_MS=$((sec * 1000 + 10#$frac / 1000))
    fi
}

mark() { # mark <name> <start_ms> <end_ms>
    printf '%s\t%s\t%s\n' "$1" "$2" "$3" >>"$MARKS"
}

echo "profiler-control: sampling every ${INTERVAL}s into $TSV"
PROFILER_DISK_EVERY_S=10 PROFILER_RUNNER_LABEL=control \
    bash "$SAMPLER" --out "$TSV" --interval "$INTERVAL" &
SAMPLER_PID=$!
sleep "$((INTERVAL * 2))"

# --- phase 1: exactly one busy core ---------------------------------------
# A bash `while :; do :; done` is one process spinning in userspace, which is
# the cleanest single-core load available without a compiler.
echo "profiler-control: phase 1 BUSY (${BUSY_S}s)"
now_ms
P1_START="$NOW_MS"
bash -c 'while :; do :; done' &
BUSY_PID=$!
sleep "$BUSY_S"
kill "$BUSY_PID" 2>/dev/null
wait "$BUSY_PID" 2>/dev/null
BUSY_PID=""
now_ms
mark BUSY "$P1_START" "$NOW_MS"

# --- phase 2: idle ---------------------------------------------------------
echo "profiler-control: phase 2 IDLE (${IDLE_S}s)"
now_ms
P2_START="$NOW_MS"
sleep "$IDLE_S"
now_ms
mark IDLE "$P2_START" "$NOW_MS"

# --- phase 3: 512 MiB anonymous ---------------------------------------------
echo "profiler-control: phase 3 ALLOC 512 MiB anonymous (${ALLOC_S}s)"
now_ms
P3_START="$NOW_MS"
CHUNK=""
build_chunk() {
    local unit i
    unit="$(printf 'x%.0s' {1..65536})"
    CHUNK=""
    for ((i = 0; i < 16; i++)); do CHUNK="$CHUNK$unit"; done
}
build_chunk
declare -a HOLD=()
for ((i = 0; i < 512; i++)); do HOLD[i]="$CHUNK"; done
sleep "$ALLOC_S"
now_ms
mark ALLOC "$P3_START" "$NOW_MS"
unset HOLD
unset CHUNK

# --- phase 4: 1 GiB on disk -------------------------------------------------
echo "profiler-control: phase 4 DISK 1 GiB (${DISK_S}s)"
now_ms
P4_START="$NOW_MS"
if ! dd if=/dev/zero of="$BLOB" bs=1M count=1024 status=none 2>"$WORK/dd.err"; then
    echo "profiler-control: dd failed: $(cat "$WORK/dd.err")" >&2
    exit 2
fi
sync
sleep "$DISK_S"
now_ms
mark DISK "$P4_START" "$NOW_MS"
rm -f "$BLOB"

kill "$SAMPLER_PID" 2>/dev/null
wait "$SAMPLER_PID" 2>/dev/null
SAMPLER_PID=""

# --- evaluation -------------------------------------------------------------
# Phase windows are trimmed by one interval at each end: the sample straddling a
# boundary contains both phases and would blur every verdict.
awk -v interval="$INTERVAL" '
    function fmt(v) { return sprintf("%.2f", v) }
    FILENAME == marks {
        pn[++np] = $1; ps[$1] = $2; pe[$1] = $3
        next
    }
    $1 == "#META" { tier = $2; next }
    $1 == "S" {
        n++; t[n] = $2 + 0; cpu[n] = $3 + 0; mem[n] = $4 + 0; ws[n] = $7 + 0
        if (base_mem == 0 || mem[n] < base_mem) base_mem = mem[n]
        if (ws[n] > 0 && (base_ws == 0 || ws[n] < base_ws)) base_ws = ws[n]
    }
    END {
        if (n < 8) { print "FAIL setup: only " n " samples collected"; exit 1 }
        lead = interval * 1000
        # Pass 1: per-phase statistics. The sample straddling a boundary holds
        # both phases and would blur every verdict, so a full interval is
        # trimmed from each end of the window.
        for (p = 1; p <= np; p++) {
            name = pn[p]; lo = ps[name] + lead; hi = pe[name] - lead
            cnt = 0; sum = 0; mx = 0; mxws = 0
            for (i = 1; i <= n; i++) {
                if (t[i] < lo || t[i] > hi) continue
                cnt++; sum += cpu[i]
                if (mem[i] > mx) mx = mem[i]
                if (ws[i] > mxws) mxws = ws[i]
            }
            c_cnt[name] = cnt
            c_cpu[name] = cnt > 0 ? (sum / cnt) / 1000 : 0
            c_mem[name] = (mx - base_mem) / 1048576
            c_ws[name] = (mxws - base_ws) / 1024
        }
        # Pass 2: verdicts. BUSY is checked as a DELTA over IDLE, not as an
        # absolute. On a cgroup runner the two are the same thing; on a shared
        # machine at PROC_HOST tier the absolute reading includes every other
        # process on the box, and an instrument check that fails because the
        # laptop was busy is testing the laptop.
        # At PROC_HOST tier the sampler has no cgroup to scope to and is reading
        # the whole machine, so every CPU and RAM verdict here is really a
        # verdict on whatever else the box is doing. Those phases are reported
        # with their numbers and marked SKIP, and the run ends INCONCLUSIVE (2)
        # rather than green: "could not be judged" must not read as "passed".
        # Disk survives, because `df` measures the filesystem and a 1 GiB write
        # dominates anything a busy machine does around it.
        host_tier = (tier == "PROC_HOST")
        for (p = 1; p <= np; p++) {
            name = pn[p]
            if (c_cnt[name] == 0) { print "FAIL " name ": no samples inside the phase window"; bad++; continue }
            ok = 1
            if (name == "BUSY") {
                d = c_cpu["BUSY"] - c_cpu["IDLE"]
                if (host_tier) { skipped++; verdict = "SKIP" } else { ok = (d >= 0.85 && d <= 1.15); verdict = ok ? "PASS" : "FAIL" }
                printf "%s BUSY: +%s cores over idle (%s busy, %s idle) across %d samples (expect 1.00 +/- 0.15)\n",
                    verdict, fmt(d), fmt(c_cpu["BUSY"]), fmt(c_cpu["IDLE"]), c_cnt[name]
            } else if (name == "IDLE") {
                if (host_tier) { skipped++; verdict = "SKIP" } else { ok = (c_cpu["IDLE"] < 0.25); verdict = ok ? "PASS" : "FAIL" }
                printf "%s IDLE: mean %s cores across %d samples (expect < 0.25)\n",
                    verdict, fmt(c_cpu["IDLE"]), c_cnt[name]
            } else if (name == "ALLOC") {
                if (host_tier) { skipped++; verdict = "SKIP" } else { ok = (c_mem[name] >= 400 && c_mem[name] <= 640); verdict = ok ? "PASS" : "FAIL" }
                printf "%s ALLOC: +%s MiB above baseline across %d samples (expect 400-640)\n",
                    verdict, fmt(c_mem[name]), c_cnt[name]
            } else if (name == "DISK") {
                ok = (c_ws[name] >= 870 && c_ws[name] <= 1178)
                printf "%s DISK: +%s MiB above baseline across %d samples (expect 870-1178)\n",
                    ok ? "PASS" : "FAIL", fmt(c_ws[name]), c_cnt[name]
            }
            if (!ok) bad++
        }
        printf "tier: %s, samples: %d\n", tier, n
        if (bad > 0) exit 1
        if (skipped > 0) {
            print "CONTROL INCONCLUSIVE: " skipped " phase(s) were skipped because this run is at PROC_HOST tier."
            print "CPU and RAM here describe the whole machine, not the workload. Run this on a runner"
            print "with a real cgroup quota (ubuntu-slim, or any container) for a verdict on those three."
            exit 2
        }
        exit 0
    }
' marks="$MARKS" "$MARKS" "$TSV"
RC=$?
exit "$RC"
