# Aggregate a sampler-linux.sh TSV into the job's markdown summary panel.
#
# WHY THIS IS AWK: the post hook runs on a runner that may be a 1-vCPU
# container, and awk is the one text tool guaranteed present next to bash.
# Written for MAWK (Ubuntu's /usr/bin/awk), so: no asort, no length(array), no
# strtonum, no gensub, and byte counts printed with %.0f rather than %d because
# mawk's integer conversion truncates above 2^31.
#
# ANTI-VACUITY IS THE POINT. A profiler that silently collected nothing and then
# printed a clean-looking flat-zero profile is worse than no profiler: it
# launders "we measured nothing" into "this job uses no CPU", and a job would be
# moved on the strength of it. So every degenerate shape is a FINDING, written
# to findings_file and reported by exit 1:
#   - fewer than 3 samples, or fewer than 0.8x the expected count
#   - every CPU sample zero
#   - every RAM sample identical
#   - a HOST_LEAK meta line (the sampler read the host, not the container)
# The one shape that is NOT a finding is a run shorter than one sample interval:
# nothing COULD have been sampled, so it is reported as "<interval, unsampled",
# never as 0.
#
# Usage (via panel.sh):
#   awk -v wall_s=<seconds> -v findings_file=<path> -v title=<text> \
#       -f report.awk <samples.tsv>
#
# Variables:
#   wall_s         real elapsed seconds from the action (authoritative; falls
#                  back to the sample span when absent, which UNDERSTATES a run
#                  whose sampler died early -- that is why the action passes it)
#   findings_file  anti-vacuity findings, one per line (empty file = clean)
#   title          panel heading suffix, e.g. the job name
#   declared_s     declared timeout in seconds (default 840 = 14 min)
#   hard_s         platform hard cap in seconds (default 900 = 15 min, slim)
#
# Exit: 0 clean, 1 one or more findings.

function fmt_cores(milli) { return sprintf("%.2f", milli / 1000) }

function fmt_bytes(b) {
    if (b >= 1073741824) return sprintf("%.2f GiB", b / 1073741824)
    if (b >= 1048576) return sprintf("%.0f MiB", b / 1048576)
    if (b >= 1024) return sprintf("%.0f KiB", b / 1024)
    return sprintf("%.0f B", b)
}

function pct(a, b) { return b > 0 ? sprintf("%.0f%%", 100 * a / b) : "n/a" }

function hms(s,   h, m) {
    h = int(s / 3600); m = int((s % 3600) / 60)
    if (h > 0) return sprintf("%dh %dm %ds", h, m, s % 60)
    if (m > 0) return sprintf("%dm %ds", m, s % 60)
    return sprintf("%ds", s)
}

function qsort(arr, lo, hi,   i, j, p, t) {
    if (lo >= hi) return
    p = arr[int((lo + hi) / 2)]; i = lo; j = hi
    while (i <= j) {
        while (arr[i] < p) i++
        while (arr[j] > p) j--
        if (i <= j) { t = arr[i]; arr[i] = arr[j]; arr[j] = t; i++; j-- }
    }
    qsort(arr, lo, j); qsort(arr, i, hi)
}

# p95 over a 1-indexed array of n values, nearest-rank.
function p95(arr, n,   idx) {
    if (n < 1) return 0
    qsort(arr, 1, n)
    idx = int(0.95 * n + 0.9999)
    if (idx < 1) idx = 1
    if (idx > n) idx = n
    return arr[idx]
}

function finding(msg) {
    findings[++nfind] = msg
    if (findings_file != "") print msg > findings_file
}

BEGIN {
    FS = "\t"
    if (declared_s == "") declared_s = 840
    if (hard_s == "") hard_s = 900
    tier = "UNKNOWN"; cpu_ceil = 0; mem_ceil = 0; interval = 0
    runner = "unknown"; cpu_src = "?"; mem_src = "?"
    n = 0; nfind = 0
    cpu_sum = 0; cpu_peak = 0; cpu_nonzero = 0
    mem_sum = 0; mem_peak = 0; mem_min = -1
    prev_rx = -1; prev_tx = -1; gaps = 0; prev_t = -1
    t0 = -1; tlast = -1
}

$1 == "#META" {
    tier = $2; cpu_ceil = $3 + 0; mem_ceil = $4 + 0; interval = $5 + 0
    start_ms = $6 + 0; runner = $7; cpu_src = $8; mem_src = $9
    # Field 10 is newer than the rest; an older TSV simply leaves it empty, which
    # reads as UNKNOWN and changes nothing.
    container_hint = ($10 == "") ? "UNKNOWN" : $10
    next
}

$1 == "S" {
    n++
    t = $2 + 0; c = $3 + 0; m = $4 + 0; rx = $5 + 0; tx = $6 + 0
    dws = $7 + 0; dtmp = $8 + 0
    if (t0 < 0) t0 = t
    tlast = t
    cpu_v[n] = c; mem_v[n] = m; ts[n] = t
    cpu_sum += c; mem_sum += m
    if (c > cpu_peak) cpu_peak = c
    if (c > 0) cpu_nonzero++
    if (m > mem_peak) mem_peak = m
    if (mem_min < 0 || m < mem_min) mem_min = m
    drx = (prev_rx >= 0 && rx >= prev_rx) ? rx - prev_rx : 0
    dtx = (prev_tx >= 0 && tx >= prev_tx) ? tx - prev_tx : 0
    prev_rx = rx; prev_tx = tx
    rx_d[n] = drx; tx_d[n] = dtx
    ws_v[n] = dws; tmp_v[n] = dtmp
    if (dws > ws_peak) ws_peak = dws
    if (dtmp > tmp_peak) tmp_peak = dtmp
    if (prev_t >= 0 && interval > 0 && (t - prev_t) > 1500 * interval) gaps++
    prev_t = t
}

END {
    if (interval <= 0) interval = 10

    # Wall clock: the action's measurement wins. Falling back to the sample span
    # would hide exactly the failure worth catching -- a sampler that died at
    # minute two of a twelve-minute job looks like a two-minute job.
    span_s = (n > 1) ? int((tlast - t0) / 1000) + interval : 0
    if (wall_s + 0 > 0) wall = wall_s + 0; else wall = span_s
    if (wall < 0) wall = 0

    print ""
    print "## Runner Profile" (title != "" ? ": " title : "")
    print ""
    print "**Runner:** " runner " (tier " tier "; cpu via " cpu_src ", memory via " mem_src ")"
    print "**Detected ceilings:** " fmt_cores(cpu_ceil) " cores / " fmt_bytes(mem_ceil)
    print "**Wall clock:** " hms(wall) " (" pct(wall, declared_s) " of the 14m declared timeout, " \
          pct(wall, hard_s) " of the 15m slim hard cap)"

    if (tier == "HOST_LEAK") {
        finding("HOST_LEAK: the sampler resolved host-sized limits (" fmt_cores(cpu_ceil) \
                " cores / " fmt_bytes(mem_ceil) ") on runner '" runner "'. No profile was written.")
        print "**Samples:** none - the sampler refused to run."
        print ""
        print "> HOST_LEAK. The cgroup read fell through to the host, so the numbers"
        print "> this runner reports describe the machine, not the container. Nothing"
        print "> is profiled and nothing should be concluded."
        exit_code = 1
        finish()
    }

    # A step shorter than one interval could not be sampled. Saying "0 cores" here
    # would be a lie the size of the whole job.
    if (wall > 0 && wall < interval) {
        print "**Samples:** <interval, unsampled (ran " hms(wall) ", sample interval " interval "s)"
        print ""
        print "> Shorter than one sample interval, so no profile exists. This is NOT"
        print "> a zero-usage job; it is an unmeasured one."
        exit_code = 0
        finish()
    }

    # The first sample lands one full interval IN, not at t=0, so a W-second run
    # yields int(W/interval) samples, not one more. The off-by-one version fired
    # the starvation finding on a perfectly healthy 7-second capture (6 of "8"),
    # which is the kind of false alarm that gets an anti-vacuity check disabled.
    expected = int(wall / interval)
    if (expected < 1) expected = 1
    print "**Samples:** " n " of ~" expected " expected (" gaps " gap" (gaps == 1 ? "" : "s") ")"

    if (n == 0) {
        finding("no samples: the sampler wrote a meta line but never a single reading over " hms(wall) ".")
        print ""
        print "> No samples. The sampler started and produced nothing, so there is no"
        print "> profile - not a flat one."
        exit_code = 1
        finish()
    }
    if (n < 3) {
        finding("sample floor: " n " sample(s) over " hms(wall) " is below the hard floor of 3.")
    } else if (n < 0.8 * expected) {
        finding("sample floor: " n " samples is below 0.8x the " expected " expected over " hms(wall) \
                "; the sampler was starved or died early.")
    }
    if (cpu_nonzero == 0) {
        finding("degenerate CPU series: every one of " n " CPU samples is exactly zero, which means the counter was never read, not that the job was idle.")
    }
    if (mem_peak == mem_min) {
        finding("degenerate RAM series: all " n " RAM samples are identical (" fmt_bytes(mem_peak) \
                "), which means a constant was recorded rather than a measurement.")
    }
    # A WRONG label is more dangerous than a missing one. HOST_LEAK is armed off
    # the label, so a slim job mislabelled ubuntu-latest skips it entirely, and
    # everything downstream then treats host-sized ceilings as the job's own.
    # The container fingerprint is the only thing that can contradict a label
    # that lies, so when it does, that is a finding and the advisory goes quiet.
    if (tier == "PROC_HOST" && container_hint == "CONTAINER" && runner !~ /slim/ &&
        runner != "" && runner != "unknown") {
        finding("MISLABEL SUSPECTED: the label says '" runner "' but this process is running in a container " \
                "(PID 1 fingerprint), and the limits came from /proc -- so the " fmt_cores(cpu_ceil) \
                " cores / " fmt_bytes(mem_ceil) " below belong to the HOST, not to this job. " \
                "HOST_LEAK could not fire because it is armed off the label.")
    }

    bucket = (wall > 3600) ? 300 : 60
    nb = 0
    for (i = 1; i <= n; i++) {
        b = int((ts[i] - t0) / (bucket * 1000))
        if (!(b in b_seen)) { b_seen[b] = 1; b_order[++nb] = b; b_cpu_peak[b] = 0; b_mem_peak[b] = 0 }
        b_cnt[b]++
        b_cpu_sum[b] += cpu_v[i]
        if (cpu_v[i] > b_cpu_peak[b]) b_cpu_peak[b] = cpu_v[i]
        b_mem_sum[b] += mem_v[i]
        if (mem_v[i] > b_mem_peak[b]) b_mem_peak[b] = mem_v[i]
        b_rx[b] += rx_d[i]; b_tx[b] += tx_d[i]
        if (ws_v[i] > 0) b_ws[b] = ws_v[i]
    }

    print ""
    print "| " (bucket == 60 ? "Minute" : "Minutes") " | CPU mean | CPU peak | RAM mean | RAM peak | Disk (ws) | Net rx | Net tx |"
    print "|---|---|---|---|---|---|---|---|"
    for (j = 1; j <= nb; j++) {
        b = b_order[j]
        lo = b * (bucket / 60); hi = lo + (bucket / 60)
        printf "| %02d-%02d | %s | %s | %s | %s | %s | %s | %s |\n", lo, hi,
            fmt_cores(b_cpu_sum[b] / b_cnt[b]), fmt_cores(b_cpu_peak[b]),
            fmt_bytes(b_mem_sum[b] / b_cnt[b]), fmt_bytes(b_mem_peak[b]),
            (b_ws[b] > 0 ? fmt_bytes(b_ws[b] * 1024) : "-"),
            fmt_bytes(b_rx[b]), fmt_bytes(b_tx[b])
    }

    cpu_mean = cpu_sum / n
    mem_mean = mem_sum / n
    cpu_p95 = p95(cpu_v, n)
    mem_p95 = p95(mem_v, n)

    print ""
    print "**CPU:** mean " fmt_cores(cpu_mean) " (" pct(cpu_mean, cpu_ceil) " of ceiling) / p95 " \
          fmt_cores(cpu_p95) " / peak " fmt_cores(cpu_peak) " cores"
    print "**RAM:** mean " fmt_bytes(mem_mean) " (" pct(mem_mean, mem_ceil) " of ceiling) / p95 " \
          fmt_bytes(mem_p95) " / peak " fmt_bytes(mem_peak)
    # Slim's whole disk is 14 GB, image included, so filesystem-used peaks are a
    # sizing constraint in their own right and not decoration. When workspace and
    # runner temp sit on one filesystem the two figures are the same number, and
    # saying so is cheaper than letting someone add them together.
    print "**Disk peak (filesystem used):** workspace " fmt_bytes(ws_peak * 1024) \
          (ws_peak == tmp_peak ? " (runner temp is the same filesystem)" \
                               : ", runner temp " fmt_bytes(tmp_peak * 1024))
    print "**Headroom:** " pct(declared_s - wall, declared_s) " under the declared timeout, " \
          pct(hard_s - wall, hard_s) " under the slim hard cap"
    print "**Advisory:** " advise(tier, cpu_peak, mem_peak, wall, runner)
    exit_code = (nfind > 0) ? 1 : 0
    finish()
}

# The advisory is the whole point of the tool, so it refuses to speak from
# untrustworthy inputs rather than guessing. Slim is recommended WHEREVER IT
# FITS: on this public repo standard runners are free, so an oversized runner
# costs no money and roughly 4x the core-minutes.
#
# PROC_HOST IS NOT AUTOMATICALLY UNTRUSTWORTHY, and getting this backwards would
# have muted the advisor on every ubuntu-latest job -- which is the entire
# population this tool exists to triage. ubuntu-latest is a real VM the job owns
# outright, so /proc IS its ceiling: host-wide and job-wide are the same numbers.
# The reading is only poisoned when /proc is read from INSIDE a container, which
# is the slim case, and there the sampler has already refused (a slim label plus
# host-sized limits is HOST_LEAK). What remains genuinely ambiguous is PROC_HOST
# with no label at all: a VM and a container are indistinguishable from here, so
# that one says nothing.
#
# THE LABEL ONLY MATTERS WHEN THE CGROUP READ FAILED. When it succeeded, the
# detected CEILING is itself the ground truth about the box: a 1-core / 5 GB
# quota is a slim-sized container whatever anyone called it. So an unlabelled
# job at a cgroup tier is still advisable, and is judged by its ceiling rather
# than assumed not-slim -- without this, an unlabelled slim job that fits was
# told to "MOVE TO ubuntu-slim" while already sitting on one. This is the
# label-free signal, and unlike container fingerprinting it needs no probe data
# to be trusted, because it is the quota the kernel is enforcing.
function advise(tier, cpk, mpk, w, rn,   caveat, unlabelled, on_slim) {
    # States the ASSUMPTION rather than asserting the fact. The old wording --
    # "valid because 'X' is a full VM" -- was a claim the report has no way to
    # verify: its only evidence is the label, and the label is exactly what is
    # wrong in the case that matters.
    caveat = (tier == "PROC_HOST") ? " (measured from /proc, on the assumption that '" rn "' is a full VM this job owns; if it ran in a container these are host numbers)" : ""
    unlabelled = (rn == "" || rn == "unknown")
    if (tier == "PROC_HOST" && unlabelled)
        return "none. Limits came from /proc (host-wide) and no runner label was passed, so a VM cannot be told from a container and these ceilings may belong to the host. Pass runner-label to the action."
    if (tier == "PROC_HOST" && rn ~ /slim/)
        return "none. /proc was read from inside slim's container, so these are host numbers. This should have been caught as HOST_LEAK."
    if (tier == "PROC_HOST" && container_hint == "CONTAINER")
        return "none. The label says '" rn "' but the PID 1 fingerprint says container, so the /proc ceilings are the host's. Fix the label before trusting any sizing from this run."
    # Keyed on the TIER, not on whether a label happened to be supplied. The
    # first version said `unlabelled &&`, which quietly made the ceiling
    # evidence conditional on nobody having claimed otherwise -- so a job under a
    # kernel-enforced 1-core/5GB quota but labelled ubuntu-latest was told it was
    # "on a 4-vCPU VM" and should move to slim, which is where it already was.
    # A label is a claim; an enforced quota is a fact, and the fact wins.
    #
    # Restricted to cgroup tiers deliberately: there the number is a quota the
    # kernel enforces on THIS job. At PROC_HOST it is merely how big the machine
    # is, which says nothing about what the job is confined to, and the PROC_HOST
    # branches above already handle every label case. Note this is a strict
    # generalisation -- PROC_HOST + unlabelled returns above, so the old
    # `unlabelled` clause was only ever reachable at a cgroup tier anyway.
    on_slim = (rn ~ /slim/) || (tier != "PROC_HOST" && cpu_ceil > 0 && cpu_ceil <= 1500 && mem_ceil > 0 && mem_ceil <= 6442450944)
    if (on_slim) {
        if (w >= 840) return "already on slim, but wall clock is at or past the 14m declared timeout - this job is close to the 15m hard cap and should move UP."
        if (cpk > 1000 || mpk > 4831838208) return "already on slim and saturating it (peak " fmt_cores(cpk) " cores / " fmt_bytes(mpk) "); consider moving UP if the job is slow."
        return "slim fits: peak " fmt_cores(cpk) " cores and " fmt_bytes(mpk) " inside a 1 core / 5 GB box, finishing in " hms(w) "."
    }
    if (w >= 780)
        return "keep " rn ": " hms(w) " leaves too little margin under slim's 15m hard cap." caveat
    if (cpk > 1000)
        return "keep " rn ": peak " fmt_cores(cpk) " cores needs more than slim's single vCPU." caveat
    if (mpk > 4831838208)
        return "keep " rn ": peak " fmt_bytes(mpk) " is too close to slim's 5 GB." caveat
    return "MOVE TO ubuntu-slim: peak " fmt_cores(cpk) " cores and " fmt_bytes(mpk) " fit a 1 core / 5 GB box, and " hms(w) " fits the 15m cap. On a 4-vCPU VM this job is burning about 4x the core-minutes it needs." caveat
}

function finish() {
    print ""
    if (nfind > 0) {
        print "**Profile findings:**"
        for (k = 1; k <= nfind; k++) print "- " findings[k]
        print ""
    }
    exit exit_code
}
