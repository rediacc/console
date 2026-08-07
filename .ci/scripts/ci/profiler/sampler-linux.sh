#!/bin/bash
# Sample this Linux runner's CPU / RAM / disk / network into a TSV log.
#
# WHY: standard runners are free and unlimited on this public repo, so the cost
# of a mis-sized job is not money or wall clock, it is core-minutes burned for
# nothing. A job that uses ~1 core on a 4-vCPU ubuntu-latest VM burns roughly 4x
# the cores it needs. Deciding which jobs fit ubuntu-slim (1 vCPU / 5 GB /
# 14 GB disk, hard 15-minute cap) needs measurements, not guesses.
#
# CGROUP-FIRST, deliberately. ubuntu-slim runs in an UNPRIVILEGED CONTAINER, not
# a VM. Inside a container `nproc` and /proc/meminfo report the HOST, so an
# advisor fed from /proc would read 4 cores / 16 GB on a 1-core / 5 GB runner and
# be confidently wrong in the one direction that matters. Every sample therefore
# carries the tier it was resolved at (CGROUP_V2 | CGROUP_V1 | PROC_HOST), and
# the report refuses to advise from PROC_HOST numbers.
#
# NO FORKS IN THE SAMPLE LOOP. Every reading is a `read < file` builtin plus
# $(( )) arithmetic; timestamps come from $EPOCHREALTIME, and the inter-sample
# wait is a `read -t` on a fifo rather than /bin/sleep. On 1 vCPU the fork-free
# loop costs ~1 ms per sample against 15-30 ms for a $(cat)+awk equivalent, and a
# profiler that perturbs a 1-core runner is measuring itself. Disk is the one
# exception: `df` is an external command, so it is sampled on a decimated
# cadence (about once a minute) rather than every tick.
#
# Usage:
#   .ci/scripts/ci/profiler/sampler-linux.sh --out <file> [--interval <sec>]
#   .ci/scripts/ci/profiler/sampler-linux.sh --probe
#
# Optional env (flags win):
#   PROFILER_INTERVAL      seconds between samples (default 10)
#   PROFILER_OUT           TSV output path
#   PROFILER_RUNNER_LABEL  runner label, e.g. ubuntu-slim (default $RUNNER_LABEL)
#   PROFILER_MAX_SECONDS   self-terminate after this long (default 21600 = 6h,
#                          GitHub's own job ceiling; stops an orphan running forever)
#   PROFILER_DISK_EVERY_S  seconds between `df` calls (default 60)
#   PROFILER_CGROUP_ROOT   cgroup mount to read (default /sys/fs/cgroup; test seam)
#
# Run locally:
#   .ci/scripts/ci/profiler/sampler-linux.sh --probe
#   PROFILER_RUNNER_LABEL=self .ci/scripts/ci/profiler/sampler-linux.sh \
#     --out /tmp/p.tsv --interval 2 &
#
# Output format (TSV, one line per record):
#   #META  tier  cpu_milli  mem_bytes  interval_s  start_ms  runner_label  cpu_src  mem_src  container_hint
#   S      t_ms  cpu_milli  mem_bytes  rx_bytes    tx_bytes  disk_ws_kb    disk_tmp_kb
# cpu_milli on a sample line is USAGE in millicores (1000 = one full core); on
# the #META line it is the detected CEILING.
#
# Shell options: `set -e` is deliberately NOT used. The inter-sample wait is a
# `read -t` that returns non-zero BY DESIGN on every single tick, and several
# probes legitimately fail on runners that lack a given cgroup file. Every
# fallible call below is checked explicitly instead.

set -uo pipefail
# EPOCHREALTIME renders its fraction with the LOCALE's radix character; under a
# comma locale "1690000000,123456" would break the ${x%.*} split below and every
# timestamp with it.
export LC_ALL=C

INTERVAL="${PROFILER_INTERVAL:-10}"
OUT="${PROFILER_OUT:-}"
RUNNER_LABEL="${PROFILER_RUNNER_LABEL:-${RUNNER_LABEL:-unknown}}"
MAX_SECONDS="${PROFILER_MAX_SECONDS:-21600}"
CG="${PROFILER_CGROUP_ROOT:-/sys/fs/cgroup}"
WS_DIR="${GITHUB_WORKSPACE:-$PWD}"
TMP_DIR="${RUNNER_TEMP:-/tmp}"
MODE="sample"

# ubuntu-slim is 1 vCPU / 5 GB. Anything materially above that on a slim runner
# means the cgroup read failed open and we are looking at the host.
SLIM_MEM_CEILING=$((6 * 1024 * 1024 * 1024))
SLIM_CPU_CEILING_MILLI=1500

usage() {
    sed -n '2,40p' "$0" | sed 's/^# \?//'
}

while (($# > 0)); do
    case "$1" in
        --out)
            OUT="${2:-}"
            shift 2
            ;;
        --interval)
            INTERVAL="${2:-}"
            shift 2
            ;;
        --probe)
            MODE="probe"
            shift
            ;;
        --help | -h)
            usage
            exit 0
            ;;
        *)
            echo "sampler-linux.sh: unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

case "$INTERVAL" in
    '' | *[!0-9]*)
        echo "sampler-linux.sh: --interval must be a whole number of seconds, got '$INTERVAL'" >&2
        exit 2
        ;;
esac
if [ "$INTERVAL" -lt 1 ]; then
    echo "sampler-linux.sh: --interval must be >= 1, got '$INTERVAL'" >&2
    exit 2
fi

# $EPOCHREALTIME is the whole reason the loop is fork-free; without it every
# sample would need a `date` fork and the profiler would cost more than the work
# it measures on a 1-vCPU runner.
if [ -z "${EPOCHREALTIME:-}" ]; then
    echo "sampler-linux.sh: bash >= 5.0 required (\$EPOCHREALTIME is unset; this bash is ${BASH_VERSION:-unknown})" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Ceiling resolution (once, at startup)
# ---------------------------------------------------------------------------

CPU_CEIL_MILLI=0
MEM_CEIL_BYTES=0
CPU_SRC="" # CGROUP_V2 | CGROUP_V1 | PROC_HOST
MEM_SRC=""
CPU_MODE="" # how to read usage each tick
MEM_MODE=""

is_num() {
    case "${1:-}" in
        '' | *[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

detect_cpu_ceiling() {
    local q p n
    if [ -r "$CG/cpu.max" ] && read -r q p <"$CG/cpu.max"; then
        CPU_MODE="V2"
        if is_num "$q" && is_num "${p:-}" && [ "${p:-0}" -gt 0 ]; then
            CPU_CEIL_MILLI=$((q * 1000 / p))
            CPU_SRC="CGROUP_V2"
            return 0
        fi
        # "max <period>": the cgroup exists but imposes no quota, so the real
        # ceiling is the host's core count. That is a HOST reading, and on slim
        # it is exactly the leak this script refuses to advise from.
    elif [ -r "$CG/cpu/cpu.cfs_quota_us" ] && read -r q <"$CG/cpu/cpu.cfs_quota_us"; then
        CPU_MODE="V1"
        if read -r p <"$CG/cpu/cpu.cfs_period_us" && is_num "$q" && is_num "$p" && [ "$p" -gt 0 ]; then
            CPU_CEIL_MILLI=$((q * 1000 / p))
            CPU_SRC="CGROUP_V1"
            return 0
        fi
    fi
    n="$(nproc 2>/dev/null || echo 0)"
    is_num "$n" || n=0
    [ "$n" -gt 0 ] || n=1
    CPU_CEIL_MILLI=$((n * 1000))
    CPU_SRC="PROC_HOST"
}

detect_mem_ceiling() {
    local v k
    if [ -r "$CG/memory.max" ] && read -r v <"$CG/memory.max"; then
        MEM_MODE="V2"
        if is_num "$v" && [ "$v" -gt 0 ]; then
            MEM_CEIL_BYTES="$v"
            MEM_SRC="CGROUP_V2"
            return 0
        fi
    elif [ -r "$CG/memory/memory.limit_in_bytes" ] && read -r v <"$CG/memory/memory.limit_in_bytes"; then
        MEM_MODE="V1"
        # cgroup v1 spells "unlimited" as a number near 2^63, not as a word.
        if is_num "$v" && [ "$v" -gt 0 ] && [ "$v" -lt 4611686018427387904 ]; then
            MEM_CEIL_BYTES="$v"
            MEM_SRC="CGROUP_V1"
            return 0
        fi
    fi
    while read -r k v _; do
        if [ "$k" = "MemTotal:" ]; then
            is_num "$v" && MEM_CEIL_BYTES=$((v * 1024))
            break
        fi
    done </proc/meminfo
    MEM_SRC="PROC_HOST"
}

# Container fingerprint. This exists because the label can be WRONG, not just
# missing: a slim job mislabelled ubuntu-latest skips the HOST_LEAK check
# entirely (that check is armed off the label) and the report then attaches a
# validity claim to host numbers. A fingerprint can only ever RAISE suspicion
# here, never certify safety -- a false negative leaves us exactly where we were,
# while a false positive is a visible warning rather than a silent wrong answer.
# That asymmetry is why this is allowed to ship before profiler-probe.yml has
# confirmed what these files look like inside slim.
CONTAINER_HINT="UNKNOWN"
detect_container() {
    local v
    if [ -e /.dockerenv ]; then
        CONTAINER_HINT="CONTAINER"
        return 0
    fi
    if [ -r /proc/1/comm ] && read -r v </proc/1/comm; then
        case "$v" in
            systemd | init) ;;
            *)
                CONTAINER_HINT="CONTAINER"
                return 0
                ;;
        esac
    else
        return 0
    fi
    if [ -r /proc/1/cgroup ] && read -r v </proc/1/cgroup; then
        case "$v" in
            "0::/" | "0::/init.scope") CONTAINER_HINT="HOST" ;;
            *) CONTAINER_HINT="CONTAINER" ;;
        esac
    fi
    return 0
}

detect_cpu_ceiling
detect_mem_ceiling
detect_container

# The tier is the WORSE of the two sources: a report is only as trustworthy as
# its least trustworthy input, and mixing a real cgroup CPU quota with a host
# MemTotal is precisely how an advisor talks confident nonsense.
if [ "$CPU_SRC" = "PROC_HOST" ] || [ "$MEM_SRC" = "PROC_HOST" ]; then
    TIER="PROC_HOST"
elif [ "$CPU_SRC" = "CGROUP_V1" ] || [ "$MEM_SRC" = "CGROUP_V1" ]; then
    TIER="CGROUP_V1"
else
    TIER="CGROUP_V2"
fi

# ---------------------------------------------------------------------------
# HOST_LEAK: hard failure, never a warning
# ---------------------------------------------------------------------------
# Reading the host's 16 GB on a 5 GB runner and then advising from it is the one
# catastrophic failure of this tool. Stopping loudly is correct; a "warning" in
# a 3000-line log is not.
check_host_leak() {
    case "$RUNNER_LABEL" in
        *slim*) ;;
        *) return 0 ;;
    esac
    if [ "$MEM_CEIL_BYTES" -le "$SLIM_MEM_CEILING" ] && [ "$CPU_CEIL_MILLI" -le "$SLIM_CPU_CEILING_MILLI" ]; then
        return 0
    fi
    HOST_LEAK_MSG="HOST_LEAK on runner label '$RUNNER_LABEL': detected memory ceiling ${MEM_CEIL_BYTES} bytes (limit ${SLIM_MEM_CEILING}) and CPU quota ${CPU_CEIL_MILLI} millicores (limit ${SLIM_CPU_CEILING_MILLI}) via tier ${TIER}. A slim runner is 1 vCPU / 5 GB; these are host numbers, so every conclusion drawn from them would be wrong."
    return 1
}

# ---------------------------------------------------------------------------
# Per-sample readings (fork-free)
# ---------------------------------------------------------------------------

CPU_USEC=0
read_cpu_usec() {
    local k v ns u n s irq sirq steal
    if [ "$CPU_MODE" = "V2" ]; then
        while read -r k v; do
            if [ "$k" = "usage_usec" ]; then
                CPU_USEC="$v"
                return 0
            fi
        done <"$CG/cpu.stat"
    elif [ "$CPU_MODE" = "V1" ] && [ -r "$CG/cpuacct/cpuacct.usage" ]; then
        if read -r ns <"$CG/cpuacct/cpuacct.usage" && is_num "$ns"; then
            CPU_USEC=$((ns / 1000))
            return 0
        fi
    fi
    # /proc/stat is in USER_HZ jiffies; 100 Hz is the value every Ubuntu runner
    # kernel ships, and this branch only feeds a PROC_HOST-tier report anyway.
    if read -r _ u n s _ _ irq sirq steal _ </proc/stat; then
        CPU_USEC=$(((u + n + s + irq + sirq + steal) * 10000))
        return 0
    fi
    return 1
}

MEM_BYTES=0
read_mem_bytes() {
    local cur k v inactive=0 total=0 avail=0
    if [ "$MEM_MODE" = "V2" ] && read -r cur <"$CG/memory.current" && is_num "$cur"; then
        while read -r k v _; do
            if [ "$k" = "inactive_file" ]; then
                inactive="$v"
                break
            fi
        done <"$CG/memory.stat"
        is_num "$inactive" || inactive=0
        MEM_BYTES=$((cur > inactive ? cur - inactive : cur))
        return 0
    fi
    if [ "$MEM_MODE" = "V1" ] && read -r cur <"$CG/memory/memory.usage_in_bytes" && is_num "$cur"; then
        while read -r k v _; do
            if [ "$k" = "total_inactive_file" ]; then
                inactive="$v"
                break
            fi
        done <"$CG/memory/memory.stat"
        is_num "$inactive" || inactive=0
        MEM_BYTES=$((cur > inactive ? cur - inactive : cur))
        return 0
    fi
    while read -r k v _; do
        case "$k" in
            MemTotal:) total="$v" ;;
            MemAvailable:)
                avail="$v"
                break
                ;;
        esac
    done </proc/meminfo
    is_num "$total" && is_num "$avail" || return 1
    MEM_BYTES=$(((total - avail) * 1024))
    return 0
}

NET_RX=0
NET_TX=0
read_net_bytes() {
    local line name rest
    NET_RX=0
    NET_TX=0
    while read -r line; do
        case "$line" in
            *:*) ;;
            *) continue ;;
        esac
        name="${line%%:*}"
        rest="${line#*:}"
        name="${name// /}"
        # The kernel prints "%6s:%8llu", so once rx_bytes exceeds 8 digits the
        # colon is glued to the number and a naive field split reads "eth0:1234"
        # as the interface name. A CI job downloading 100 MB crosses that line,
        # which is why the name and the counters are split on ':' first.
        case "$name" in
            '' | lo | Inter | face) continue ;;
        esac
        # BLOCKER: intentional word splitting of a /proc line into positional
        # parameters; this is the fork-free alternative to a herestring, which
        # spills to a temp file on bash < 5.1.
        # shellcheck disable=SC2086
        set -- $rest
        if [ "$#" -ge 9 ] && is_num "$1" && is_num "$9"; then
            NET_RX=$((NET_RX + $1))
            NET_TX=$((NET_TX + $9))
        fi
    done </proc/net/dev
    return 0
}

DF_TMP=""
DISK_WS_KB=0
DISK_TMP_KB=0
DF_USED=0
df_used_kb() {
    DF_USED=0
    [ -n "$DF_TMP" ] || return 0
    df -P -k "$1" >"$DF_TMP" 2>/dev/null || return 0
    local used
    {
        read -r _ || return 0
        read -r _ _ used _ || return 0
    } <"$DF_TMP"
    is_num "${used:-}" && DF_USED="$used"
    return 0
}

read_disk_kb() {
    df_used_kb "$WS_DIR"
    DISK_WS_KB="$DF_USED"
    df_used_kb "$TMP_DIR"
    DISK_TMP_KB="$DF_USED"
}

NOW_US=0
now_us() {
    local r sec frac
    r="$EPOCHREALTIME"
    sec="${r%.*}"
    frac="${r#*.}"
    if [ "$frac" = "$r" ]; then
        NOW_US=$((sec * 1000000))
    else
        NOW_US=$((sec * 1000000 + 10#$frac))
    fi
}

# ---------------------------------------------------------------------------
# --probe: report what this runner actually is, plus the real per-sample cost
# ---------------------------------------------------------------------------

probe_file() {
    local f="$1" v
    if [ -r "$f" ] && read -r v <"$f"; then
        echo "$v"
    else
        echo "(unreadable)"
    fi
}

run_probe() {
    local t0 t1 i per_us mt
    mt="$(probe_file /proc/meminfo)"

    echo "## Runner probe: ${RUNNER_LABEL}"
    echo ""
    echo "**Runner label:** ${RUNNER_LABEL}"
    echo "**Resolved tier:** ${TIER} (cpu via ${CPU_SRC}, memory via ${MEM_SRC})"
    if [ -d "$CG" ] && [ -r "$CG" ]; then
        echo "**Cgroup mount:** ${CG} readable"
    else
        echo "**Cgroup mount:** ${CG} NOT readable"
    fi
    if [ -e "$CG/cgroup.controllers" ]; then
        echo "**Cgroup version:** v2 (cgroup.controllers present)"
    elif [ -d "$CG/cpu" ] || [ -d "$CG/memory" ]; then
        echo "**Cgroup version:** v1 (per-controller directories)"
    else
        echo "**Cgroup version:** none visible"
    fi
    echo "**cpu.max:** $(probe_file "$CG/cpu.max")"
    echo "**cpu.cfs_quota_us:** $(probe_file "$CG/cpu/cpu.cfs_quota_us")"
    echo "**memory.max:** $(probe_file "$CG/memory.max")"
    echo "**memory.limit_in_bytes:** $(probe_file "$CG/memory/memory.limit_in_bytes")"
    echo "**memory.current:** $(probe_file "$CG/memory.current")"
    echo "**nproc:** $(nproc 2>/dev/null || echo '(missing)')"
    echo "**/proc/meminfo MemTotal:** ${mt}"
    echo "**Detected CPU ceiling:** ${CPU_CEIL_MILLI} millicores"
    echo "**Detected RAM ceiling:** ${MEM_CEIL_BYTES} bytes"
    # Container fingerprints. The HOST_LEAK guard is armed by the runner LABEL
    # today, which means a caller that forgets to pass it gets no protection.
    # These are the candidates for a label-free "am I in a container" signal;
    # the probe exists to find out which of them is actually true on slim.
    echo "**RUNNER_ENVIRONMENT:** ${RUNNER_ENVIRONMENT:-(unset)}"
    echo "**/.dockerenv:** $([ -e /.dockerenv ] && echo present || echo absent)"
    echo "**/proc/1/cgroup:** $(probe_file /proc/1/cgroup)"
    echo "**/proc/1/comm:** $(probe_file /proc/1/comm)"
    echo "**awk:** $(command -v awk || echo '(missing)')"
    echo "**node:** $(command -v node || echo '(missing)')"
    echo "**df:** $(command -v df || echo '(missing)')"
    echo "**bash:** ${BASH_VERSION:-unknown}"

    DF_TMP="$(mktemp)" || DF_TMP=""
    read_disk_kb
    echo "**df workspace used:** ${DISK_WS_KB} KiB (${WS_DIR})"
    echo "**df runner temp used:** ${DISK_TMP_KB} KiB (${TMP_DIR})"

    # 100 iterations of the real per-tick work, disk excluded (disk is decimated
    # in the loop for exactly this reason).
    now_us
    t0="$NOW_US"
    i=0
    while [ "$i" -lt 100 ]; do
        read_cpu_usec
        read_mem_bytes
        read_net_bytes
        i=$((i + 1))
    done
    now_us
    t1="$NOW_US"
    per_us=$(((t1 - t0) / 100))
    echo "**Per-sample cost:** ${per_us} us over 100 iterations (cpu+mem+net, no disk)"

    if check_host_leak; then
        echo "**Host leak check:** clean"
    else
        echo "**Host leak check:** WOULD FAIL - ${HOST_LEAK_MSG}"
    fi
    [ -n "$DF_TMP" ] && rm -f "$DF_TMP"
    return 0
}

if [ "$MODE" = "probe" ]; then
    if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
        run_probe | tee -a "$GITHUB_STEP_SUMMARY"
    else
        run_probe
    fi
    exit 0
fi

# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

if [ -z "$OUT" ]; then
    echo "sampler-linux.sh: --out <file> (or PROFILER_OUT) is required" >&2
    exit 2
fi

HOST_LEAK_MSG=""
if ! check_host_leak; then
    : >"$OUT" || true
    printf '#META\tHOST_LEAK\t%s\t%s\t%s\t0\t%s\t%s\t%s\t%s\n' \
        "$CPU_CEIL_MILLI" "$MEM_CEIL_BYTES" "$INTERVAL" "$RUNNER_LABEL" "$CPU_SRC" "$MEM_SRC" \
        "$CONTAINER_HINT" >>"$OUT"
    echo "sampler-linux.sh: $HOST_LEAK_MSG" >&2
    exit 3
fi

WORK_DIR="$(mktemp -d)" || {
    echo "sampler-linux.sh: cannot create work dir" >&2
    exit 2
}
DF_TMP="$WORK_DIR/df"
FIFO="$WORK_DIR/tick"

cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

RUNNING=1
stop() { RUNNING=0; }
trap stop TERM INT

# Fork-free wait: a fifo held open read-write never delivers and never EOFs, so
# `read -t` on it is a pure-builtin sleep. /bin/sleep would be one fork per tick.
SLEEP_MODE="fifo"
if mkfifo "$FIFO" 2>/dev/null && exec 9<>"$FIFO"; then
    :
else
    SLEEP_MODE="sleep"
fi

tick_wait() {
    if [ "$SLEEP_MODE" = "fifo" ]; then
        read -r -t "$INTERVAL" -u 9 _ || true
    else
        sleep "$INTERVAL"
    fi
}

now_us
START_US="$NOW_US"
: >"$OUT" || {
    echo "sampler-linux.sh: cannot write $OUT" >&2
    exit 2
}
exec 8>>"$OUT"
printf '#META\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$TIER" "$CPU_CEIL_MILLI" "$MEM_CEIL_BYTES" "$INTERVAL" "$((START_US / 1000))" \
    "$RUNNER_LABEL" "$CPU_SRC" "$MEM_SRC" "$CONTAINER_HINT" >&8

# Disk about once a minute, and always on the first tick so the table is never
# blank for short jobs. `df` is the one fork in the loop, which is why it is
# decimated; profiler-control.sh lowers the cadence so a 1 GiB write lands
# inside a 75-second phase.
DISK_EVERY_S="${PROFILER_DISK_EVERY_S:-60}"
is_num "$DISK_EVERY_S" && [ "$DISK_EVERY_S" -ge 1 ] || DISK_EVERY_S=60
DISK_EVERY=$(((DISK_EVERY_S + INTERVAL - 1) / INTERVAL))
[ "$DISK_EVERY" -ge 1 ] || DISK_EVERY=1

read_cpu_usec || CPU_USEC=0
PREV_CPU_USEC="$CPU_USEC"
PREV_US="$START_US"
TICK=0

while [ "$RUNNING" = 1 ]; do
    tick_wait
    [ "$RUNNING" = 1 ] || break
    now_us
    read_cpu_usec || CPU_USEC="$PREV_CPU_USEC"
    read_mem_bytes || MEM_BYTES=0
    read_net_bytes

    wall_us=$((NOW_US - PREV_US))
    cpu_delta=$((CPU_USEC - PREV_CPU_USEC))
    if [ "$wall_us" -gt 0 ] && [ "$cpu_delta" -ge 0 ]; then
        cpu_milli=$((cpu_delta * 1000 / wall_us))
    else
        cpu_milli=0
    fi

    if [ $((TICK % DISK_EVERY)) -eq 0 ]; then
        read_disk_kb
    fi

    printf 'S\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$((NOW_US / 1000))" "$cpu_milli" "$MEM_BYTES" "$NET_RX" "$NET_TX" \
        "$DISK_WS_KB" "$DISK_TMP_KB" >&8

    PREV_CPU_USEC="$CPU_USEC"
    PREV_US="$NOW_US"
    TICK=$((TICK + 1))

    if [ $(((NOW_US - START_US) / 1000000)) -ge "$MAX_SECONDS" ]; then
        echo "sampler-linux.sh: reached PROFILER_MAX_SECONDS=$MAX_SECONDS, stopping" >&2
        break
    fi
done

exec 8>&-
exit 0
