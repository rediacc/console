"""Port of `.ci/scripts/test/gates/test-profiler-report.sh`.

Tests for the profiler's aggregation: `.ci/scripts/ci/profiler/report.awk` via `.ci/scripts/ci/profiler/panel.sh`, plus the sampler's own two hard refusals.

Driven entirely from SYNTHETIC sample files, so it needs no runner, no cgroup and no elapsed time. That is the point: the shapes worth testing are the ones a real run almost never produces on demand, a sampler that died at sample two, a CPU series that is all zeros, a host leak, a 350-minute job.

EVERY ANTI-VACUITY ASSERTION CARRIES ITS CONTROL. A checker that cannot fire is worth nothing, and a "the profile is clean" that is really "the checker is broken" is precisely the failure this tool exists to prevent, so each FAIL case is paired
with the near-identical PASS case it was derived from.

`GITHUB_STEP_SUMMARY` IS PINNED, NOT INHERITED, and this is the seam the twin
records paying for. panel.sh reads `SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"`
and GitHub Actions ALWAYS sets that variable, so on a runner the panel wrote to the step-summary FILE while the helper captured stdout and asserted against "". The suite passed locally (variable unset) and failed in CI for that reason alone. An unset variable is not a neutral default.

WHERE THIS REIMPLEMENTS printf, grep -c AND wc, AND WHY THE ANSWERS AGREE. The fixture writers are the twin's `printf` format strings with the same field order and the same tab separators, written through Python's `%` with the same specifiers. The two row counts are `grep -c '^| [0-9][0-9]-'` and `grep -c '^| [0-9][0-9]*-'`, which count matching LINES; the Python forms count
lines matching the same anchored patterns. `${#PANEL_OUT}` is a character count in
bash and `len()` is a character count in Python, and the panel is ASCII apart from its box drawing, so the 1 MiB ceiling means the same thing on both sides.

THE THREE LIVE CASES ARE NOT SIMULATED. `test_sampler_rejects_host_leak` drives the real sampler against a fake cgroup tree, `test_sampler_produces_a_real_profile` captures six real seconds on THIS machine, and `test_sampler_reads_a_real_containers_ceiling` proves the premise the whole advisor rests on against a kernel that is actually enforcing a quota. The last one keeps the
twin's THREE-WAY structure exactly, including its two SKIP-shaped passes, because narrowing it to the docker branch would turn the strongest proof into a silent skip the day this suite moves to ubuntu-slim (which has no docker, and which IS the container whose ceiling we care about).

NO `xdist_group`. Every case writes only into pytest's own `tmp_path`; panel.sh and the sampler are executed read-only, and the one docker invocation mounts the sampler's directory read-only and its own scratch directory read-write. Nothing is bound and no module global is mutated.
"""

import pathlib
import re
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-profiler-report.sh"

PANEL_SH = paths.from_root(".ci", "scripts", "ci", "profiler", "panel.sh")
REPORT_AWK = paths.from_root(".ci", "scripts", "ci", "profiler", "report.awk")
SAMPLER = paths.from_root(".ci", "scripts", "ci", "profiler", "sampler-linux.sh")

T0_MS = 1700000000000
CEIL_CPU = 1000
CEIL_MEM = 5 * 1024 * 1024 * 1024

STEP_SUMMARY_LIMIT = 1048576

MINUTE_ROW_RE = re.compile(r"^\| [0-9][0-9]-", re.MULTILINE)
LONG_ROW_RE = re.compile(r"^\| [0-9][0-9]*-", re.MULTILINE)


def require_subjects(gate) -> None:
    if not PANEL_SH.is_file():
        gate.log_fail("panel.sh not found at %s" % paths.relative_to_root(PANEL_SH))
    if not REPORT_AWK.is_file():
        gate.log_fail("report.awk not found at %s" % paths.relative_to_root(REPORT_AWK))


def write_meta(
    path: pathlib.Path,
    tier: str = "CGROUP_V2",
    runner: str = "ubuntu-slim",
    interval: int = 10,
    hint: str = "UNKNOWN",
    ceil_cpu: int = CEIL_CPU,
    ceil_mem: int = CEIL_MEM,
) -> None:
    """`write_meta`. TRUNCATES, as the twin's `>` does."""
    path.write_text(
        "#META\t%s\t%s\t%s\t%s\t%s\t%s\tCGROUP_V2\tCGROUP_V2\t%s\n"
        % (tier, ceil_cpu, ceil_mem, interval, T0_MS, runner, hint),
        encoding="utf-8",
    )


def write_samples(
    path: pathlib.Path, count: int, interval: int, cpu: int, mem_mb: int, step: int = 1
) -> None:
    """`write_samples`. Samples walk slightly so nothing is accidentally degenerate: a fixture that happened to be flat would make the degeneracy tests pass for the wrong reason."""
    rx = 0
    tx = 0
    rows = []
    for i in range(1, count + 1):
        rx += 100000
        tx += 50000
        rows.append(
            "S\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n"
            % (
                T0_MS + i * interval * 1000,
                cpu + (i % 5) * 10,
                (mem_mb + (i * step) % 64) * 1048576,
                rx,
                tx,
                8000000,
                900000,
            )
        )
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("".join(rows))


def run_panel(
    gate, sample_file: pathlib.Path, wall: int, strict: str = "false"
) -> harness.RunResult:
    """`run_panel <sample-file> <wall_s> <strict>`, streams MERGED (the twin's `2>&1`)."""
    require_subjects(gate)
    return harness.run(
        ["bash", str(PANEL_SH)],
        env={
            "GITHUB_STEP_SUMMARY": "/dev/stdout",
            "PROFILER_SAMPLE_FILE": str(sample_file),
            "PROFILER_WALL_S": str(wall),
            "PROFILER_STRICT": strict,
            "PROFILER_TITLE": "fixture-job",
        },
    )


def test_normal_profile_renders(gate, tmp_path):
    sample = tmp_path / "s.tsv"
    write_meta(sample)
    write_samples(sample, 37, 10, 420, 1200)
    result = run_panel(gate, sample, 370, "true")
    out = result.combined
    gate.assert_exit_code(
        0, result.rc, "a healthy profile must pass even under strict (output: %s)" % out
    )
    gate.assert_contains(out, "## Runner Profile: fixture-job", "panel carries the job title")
    gate.assert_contains(
        out, "**Runner:** ubuntu-slim (tier CGROUP_V2", "panel names runner and tier"
    )
    gate.assert_contains(out, "| Minute | CPU mean |", "per-minute table is rendered")
    gate.assert_contains(out, "**CPU:** mean", "summary block present")
    gate.assert_contains(out, "p95", "p95 is reported, not just mean and peak")
    gate.assert_contains(out, "**Advisory:**", "an advisory is emitted")
    gate.assert_not_contains(out, "::warning::", "a clean profile must not warn")
    gate.log_pass("a normal profile renders table, summary, p95 and advisory with no findings")


def test_per_minute_rows_are_per_minute(gate, tmp_path):
    # Shape check: 37 samples at 10s is ~6 minutes, so there must be 6-7 rows, not 1 and not 37. A bucketer that collapsed everything into one row would still "render a table" and pass a substring assertion.
    sample = tmp_path / "s.tsv"
    write_meta(sample)
    write_samples(sample, 37, 10, 420, 1200)
    result = run_panel(gate, sample, 370)
    rows = len(MINUTE_ROW_RE.findall(result.combined))
    if not 6 <= rows <= 7:
        gate.log_fail("expected 6-7 per-minute rows for a 370s profile, got %d" % rows)
    gate.log_pass("37 samples over ~6 minutes produce %d one-minute rows" % rows)


def test_short_sample_file_fails_the_floor(gate, tmp_path):
    sample = tmp_path / "s.tsv"
    write_meta(sample)
    write_samples(sample, 2, 10, 420, 1200)
    result = run_panel(gate, sample, 370, "true")
    gate.assert_exit_code(1, result.rc, "2 samples over 370s must fail the floor under strict")
    gate.assert_contains(result.combined, "sample floor", "names the floor it broke")
    gate.log_pass("a too-short sample file fails the anti-vacuity floor")


def test_starved_sampler_fails_the_ratio(gate, tmp_path):
    # Above the hard floor of 3, below 0.8x expected: the sampler ran but was starved or died mid-job. CONTROL: the same count with a matching wall clock passes, so the failure is the RATIO and not the count.
    starved = tmp_path / "s.tsv"
    write_meta(starved)
    write_samples(starved, 10, 10, 420, 1200)
    result = run_panel(gate, starved, 600, "true")
    gate.assert_exit_code(1, result.rc, "10 samples over a 600s job must fail 0.8x of 61 expected")
    gate.assert_contains(result.combined, "died early", "explains the sampler was starved or died")

    healthy = tmp_path / "ok.tsv"
    write_meta(healthy)
    write_samples(healthy, 10, 10, 420, 1200)
    control = run_panel(gate, healthy, 100, "true")
    gate.assert_exit_code(
        0,
        control.rc,
        "CONTROL: 10 samples over 100s is the expected count (output: %s)" % control.combined,
    )
    gate.log_pass("the 0.8x ratio fires on a starved sampler and stays silent on a short job")


def test_all_zero_cpu_fails(gate, tmp_path):
    zeros = tmp_path / "s.tsv"
    write_meta(zeros)
    with open(zeros, "a", encoding="utf-8") as handle:
        handle.writelines(
            "S\t%s\t0\t%s\t0\t0\t8000000\t900000\n"
            % (T0_MS + i * 10000, 1200 * 1048576 + i * 1048576)
            for i in range(1, 31)
        )
    result = run_panel(gate, zeros, 300, "true")
    gate.assert_exit_code(1, result.rc, "an all-zero CPU series must fail")
    gate.assert_contains(result.combined, "degenerate CPU series", "names the degenerate series")

    # CONTROL: one single non-zero CPU sample in an otherwise identical file must pass. Without this, a checker that failed EVERYTHING would look right.
    idle = tmp_path / "ok.tsv"
    write_meta(idle)
    with open(idle, "a", encoding="utf-8") as handle:
        handle.writelines(
            "S\t%s\t%s\t%s\t0\t0\t8000000\t900000\n"
            % (T0_MS + i * 10000, 30 if i == 7 else 0, 1200 * 1048576 + i * 1048576)
            for i in range(1, 31)
        )
    control = run_panel(gate, idle, 300, "true")
    gate.assert_exit_code(
        0,
        control.rc,
        "CONTROL: one non-zero CPU sample is a real (idle) profile (output: %s)" % control.combined,
    )
    gate.log_pass("all-zero CPU fails; a single non-zero reading passes")


def test_flat_ram_fails(gate, tmp_path):
    flat = tmp_path / "s.tsv"
    write_meta(flat)
    with open(flat, "a", encoding="utf-8") as handle:
        handle.writelines(
            "S\t%s\t%s\t1258291200\t0\t0\t8000000\t900000\n" % (T0_MS + i * 10000, 400 + i)
            for i in range(1, 31)
        )
    result = run_panel(gate, flat, 300, "true")
    gate.assert_exit_code(1, result.rc, "an identical-RAM series must fail")
    gate.assert_contains(result.combined, "degenerate RAM series", "names the constant RAM series")

    # CONTROL: move exactly one byte of one sample. Real memory never repeats byte
    # for byte across 30 readings; a constant means a constant was recorded.
    moved = tmp_path / "ok.tsv"
    write_meta(moved)
    with open(moved, "a", encoding="utf-8") as handle:
        handle.writelines(
            "S\t%s\t%s\t%s\t0\t0\t8000000\t900000\n"
            % (T0_MS + i * 10000, 400 + i, 1258291201 if i == 9 else 1258291200)
            for i in range(1, 31)
        )
    control = run_panel(gate, moved, 300, "true")
    gate.assert_exit_code(
        0,
        control.rc,
        "CONTROL: a one-byte difference is a measurement (output: %s)" % control.combined,
    )
    gate.log_pass("identical RAM across every sample fails; a one-byte difference passes")


def test_host_leak_fails(gate, tmp_path):
    sample = tmp_path / "s.tsv"
    write_meta(sample, "HOST_LEAK")
    result = run_panel(gate, sample, 300, "true")
    gate.assert_exit_code(1, result.rc, "a HOST_LEAK meta line must fail")
    gate.assert_contains(result.combined, "HOST_LEAK", "names the leak")
    gate.assert_not_contains(
        result.combined, "**Advisory:** MOVE TO", "a leaked profile must never advise a move"
    )
    gate.log_pass("HOST_LEAK fails and suppresses the advisory")


def test_proc_host_tier_advises_only_when_the_label_disambiguates(gate, tmp_path):
    # The direction that matters most, and the one easiest to get backwards. PROC_HOST on a real VM is TRUSTWORTHY (ubuntu-latest jobs own the whole VM, so host-wide and job-wide are the same numbers) and muting the advisor there would silence it across the entire population this tool exists to triage.
    vm = tmp_path / "vm.tsv"
    write_meta(vm, "PROC_HOST", "ubuntu-latest")
    write_samples(vm, 37, 10, 420, 1200)
    result = run_panel(gate, vm, 370, "true")
    gate.assert_exit_code(
        0, result.rc, "PROC_HOST on a VM is a valid profile (output: %s)" % result.combined
    )
    gate.assert_contains(
        result.combined,
        "**Advisory:** MOVE TO ubuntu-slim",
        "advises on a VM's own /proc numbers",
    )
    gate.assert_contains(
        result.combined, "full VM this job owns", "shows its reasoning for trusting /proc here"
    )

    unknown = tmp_path / "unknown.tsv"
    write_meta(unknown, "PROC_HOST", "unknown")
    write_samples(unknown, 37, 10, 420, 1200)
    result = run_panel(gate, unknown, 370, "true")
    gate.assert_exit_code(0, result.rc, "an unlabelled PROC_HOST profile still renders")
    gate.assert_contains(
        result.combined,
        "**Advisory:** none",
        "declines when a VM cannot be told from a container",
    )
    gate.assert_contains(result.combined, "no runner label was passed", "names the missing input")

    slim = tmp_path / "slim.tsv"
    write_meta(slim, "PROC_HOST", "ubuntu-slim")
    write_samples(slim, 37, 10, 420, 1200)
    result = run_panel(gate, slim, 370, "true")
    gate.assert_contains(
        result.combined,
        "**Advisory:** none",
        "declines when /proc was read inside slim's container",
    )
    gate.log_pass("PROC_HOST advises on a labelled VM and declines on slim or an unknown label")


def test_mislabelled_container_is_caught(gate, tmp_path):
    # The most dangerous shape of all, and the one a label-armed guard cannot see: a slim job whose label WRONGLY says ubuntu-latest. HOST_LEAK is armed off the label so it never fires, and before this check the report answered with a confident "MOVE TO ubuntu-slim". Missing labels go mute; wrong labels lie.
    mislabelled = tmp_path / "mislabelled.tsv"
    write_meta(
        mislabelled,
        "PROC_HOST",
        "ubuntu-latest",
        10,
        "CONTAINER",
        ceil_cpu=4000,
        ceil_mem=16 * 1024 * 1024 * 1024,
    )
    write_samples(mislabelled, 37, 10, 420, 1200)
    result = run_panel(gate, mislabelled, 370, "true")
    gate.assert_exit_code(1, result.rc, "a container wearing a VM label must be a finding")
    gate.assert_contains(result.combined, "MISLABEL SUSPECTED", "names the contradiction")
    gate.assert_contains(
        result.combined,
        "HOST_LEAK could not fire",
        "explains why the label-armed guard missed it",
    )
    gate.assert_contains(
        result.combined, "**Advisory:** none", "refuses to size anything from host numbers"
    )
    gate.assert_not_contains(
        result.combined, "MOVE TO ubuntu-slim", "must not recommend a move on host numbers"
    )

    # CONTROL: byte-identical except the fingerprint says HOST. A genuine VM must still get its advice, or the check would just be a blanket mute on PROC_HOST.
    genuine = tmp_path / "genuine-vm.tsv"
    write_meta(
        genuine,
        "PROC_HOST",
        "ubuntu-latest",
        10,
        "HOST",
        ceil_cpu=4000,
        ceil_mem=16 * 1024 * 1024 * 1024,
    )
    write_samples(genuine, 37, 10, 420, 1200)
    control = run_panel(gate, genuine, 370, "true")
    gate.assert_exit_code(
        0, control.rc, "CONTROL: a genuine VM is not a finding (output: %s)" % control.combined
    )
    gate.assert_contains(
        control.combined, "**Advisory:** MOVE TO ubuntu-slim", "a real VM still gets sized"
    )
    gate.assert_not_contains(control.combined, "MISLABEL", "no false alarm on a genuine VM")
    gate.log_pass("a container wearing a VM label is caught; a genuine VM is unaffected")


def test_advisory_states_its_assumption_not_a_fact(gate, tmp_path):
    # The caveat used to assert "valid because 'X' is a full VM the job owns", a claim whose only evidence was the label, i.e. the exact input that is wrong in the case above. It must state the assumption instead.
    vm = tmp_path / "vm.tsv"
    write_meta(vm, "PROC_HOST", "ubuntu-latest")
    write_samples(vm, 37, 10, 420, 1200)
    result = run_panel(gate, vm, 370, "true")
    gate.assert_contains(result.combined, "on the assumption that", "states the assumption")
    gate.assert_not_contains(
        result.combined, "valid because", "never asserts validity it cannot verify"
    )
    gate.log_pass("the PROC_HOST caveat states an assumption rather than asserting a fact")


def test_unlabelled_cgroup_job_is_sized_by_its_ceiling(gate, tmp_path):
    # The label is only load-bearing when the cgroup read FAILED. When it succeeded, the enforced quota IS the box.
    slim_sized = tmp_path / "slimsized.tsv"
    write_meta(slim_sized, "CGROUP_V2", "unknown")
    write_samples(slim_sized, 37, 10, 420, 1200)
    result = run_panel(gate, slim_sized, 370, "true")
    gate.assert_exit_code(
        0,
        result.rc,
        "an unlabelled cgroup profile still renders (output: %s)" % result.combined,
    )
    gate.assert_contains(
        result.combined,
        "**Advisory:** slim fits",
        "a 1-core/5GB quota is recognised as slim without a label",
    )
    gate.assert_not_contains(
        result.combined, "MOVE TO ubuntu-slim", "must not tell a slim job to move to slim"
    )

    # A WRONG label must lose to the enforced quota exactly as a missing one does. This was live: a job under a kernel-enforced 1-core/5GB quota, labelled ubuntu-latest, was told it was "on a 4-vCPU VM" and should move to slim, where it already was. A label is a claim; a quota is a fact.
    mislabelled = tmp_path / "mislabelled.tsv"
    write_meta(mislabelled, "CGROUP_V2", "ubuntu-latest", 10, "CONTAINER")
    write_samples(mislabelled, 37, 10, 420, 1200)
    result = run_panel(gate, mislabelled, 370, "true")
    gate.assert_exit_code(
        0, result.rc, "a mislabelled cgroup profile renders (output: %s)" % result.combined
    )
    gate.assert_contains(
        result.combined,
        "**Advisory:** slim fits",
        "the enforced quota beats a label that claims otherwise",
    )
    gate.assert_not_contains(
        result.combined,
        "MOVE TO ubuntu-slim",
        "must not tell a quota-confined job to move to slim",
    )
    gate.assert_not_contains(
        result.combined, "4x the core-minutes", "must not claim a 4-vCPU VM for a 1-core quota"
    )

    # CONTROL: same missing label, but a 4-core/16GB quota. The ceiling now says this is NOT a slim box, so the advisor must recommend the move instead.
    big = tmp_path / "vmsized.tsv"
    write_meta(
        big, "CGROUP_V2", "unknown", 10, "UNKNOWN", ceil_cpu=4000, ceil_mem=16 * 1024 * 1024 * 1024
    )
    write_samples(big, 37, 10, 420, 1200)
    control = run_panel(gate, big, 370, "true")
    gate.assert_exit_code(
        0,
        control.rc,
        "an unlabelled large-quota profile renders (output: %s)" % control.combined,
    )
    gate.assert_contains(
        control.combined,
        "**Advisory:** MOVE TO ubuntu-slim",
        "a 4-core quota that fits slim is told to move",
    )
    gate.log_pass("an unlabelled cgroup job is sized by its enforced quota, both directions")


def test_long_job_buckets_to_five_minutes(gate, tmp_path):
    sample = tmp_path / "s.tsv"
    write_meta(sample)
    # 350 minutes at one sample per 10s.
    write_samples(sample, 2100, 10, 300, 900)
    result = run_panel(gate, sample, 21000, "true")
    out = result.combined
    gate.assert_exit_code(0, result.rc, "a long healthy profile must pass (output: %s)" % out[:400])
    gate.assert_contains(out, "| Minutes | CPU mean |", "long jobs switch to a Minutes header")
    rows = len(LONG_ROW_RE.findall(out))
    if not 69 <= rows <= 71:
        gate.log_fail("expected ~70 five-minute rows for a 350-minute job, got %d" % rows)
    gate.assert_contains(out, "| 00-05 |", "first bucket spans five minutes")
    gate.assert_contains(out, "| 345-350 |", "last bucket reaches minute 350")
    size = len(out)
    if size >= STEP_SUMMARY_LIMIT:
        gate.log_fail("panel is %d bytes, over the 1 MiB step-summary limit" % size)
    gate.log_pass("a 350-minute job renders %d five-minute rows in %d bytes" % (rows, size))


def test_step_shorter_than_interval_is_unsampled_not_zero(gate, tmp_path):
    # The single most dangerous rendering: a 4-second step at a 10s interval has nothing to sample, and printing "0.00 cores" would read as "this job is free" to anyone deciding where to put it.
    sample = tmp_path / "s.tsv"
    write_meta(sample)
    result = run_panel(gate, sample, 4, "true")
    gate.assert_exit_code(
        0, result.rc, "an unsampleable step is not a finding (output: %s)" % result.combined
    )
    gate.assert_contains(
        result.combined, "<interval, unsampled", "reports the unsampled state verbatim"
    )
    gate.assert_contains(result.combined, "NOT", "spells out that this is unmeasured, not idle")
    gate.assert_not_contains(
        result.combined, "**CPU:** mean 0.00", "must never render a zero CPU summary"
    )
    gate.log_pass("a step shorter than the interval reports '<interval, unsampled', never 0")


def test_missing_sample_file_says_so(gate, tmp_path):
    missing = tmp_path / "never-written.tsv"
    result = run_panel(gate, missing, 300, "false")
    gate.assert_exit_code(0, result.rc, "a missing file warns in non-strict mode")
    gate.assert_contains(
        result.combined, "no sample file was produced", "panel says the profile is missing"
    )
    gate.assert_contains(result.combined, "::warning::", "a missing profile is annotated")
    strict = run_panel(gate, missing, 300, "true")
    gate.assert_exit_code(
        1, strict.rc, "CONTROL: strict turns the same missing file into a failure"
    )
    gate.log_pass("a missing sample file is reported as missing, and is fatal under strict")


def test_strict_flag_is_the_only_difference(gate, tmp_path):
    # The strict input is the whole failure policy, so prove it flips BOTH ways on one identical input. `continue-on-error` being banned is why this seam exists.
    sample = tmp_path / "s.tsv"
    write_meta(sample)
    write_samples(sample, 2, 10, 420, 1200)
    lenient = run_panel(gate, sample, 370, "false")
    gate.assert_exit_code(0, lenient.rc, "non-strict keeps a bad profile green")
    gate.assert_contains(lenient.combined, "::warning::profiler:", "non-strict warns")
    gate.assert_contains(lenient.combined, "## Runner Profile", "non-strict still writes the panel")
    strict = run_panel(gate, sample, 370, "true")
    gate.assert_exit_code(1, strict.rc, "strict fails on the identical input")
    gate.assert_contains(strict.combined, "::error::profiler:", "strict escalates the annotation")
    gate.log_pass("strict flips exit code and annotation level on identical input")


def test_sampler_rejects_host_leak(gate, tmp_path):
    # The sampler's own hard failure, driven through PROFILER_CGROUP_ROOT against a fake cgroup tree: a slim label plus host-sized limits must EXIT, not warn.
    if not SAMPLER.is_file():
        gate.log_fail("sampler not found at %s" % paths.relative_to_root(SAMPLER))
    cgroup = tmp_path / "cg"
    cgroup.mkdir(parents=True)
    (cgroup / "cpu.max").write_text("max 100000\n", encoding="utf-8")
    (cgroup / "memory.max").write_text("max\n", encoding="utf-8")
    (cgroup / "cpu.stat").write_text("usage_usec 100\n", encoding="utf-8")
    sample = tmp_path / "s.tsv"
    result = harness.run(
        ["bash", str(SAMPLER), "--out", str(sample), "--interval", "1"],
        env={"PROFILER_CGROUP_ROOT": str(cgroup), "PROFILER_RUNNER_LABEL": "ubuntu-slim"},
    )
    gate.assert_exit_code(
        3,
        result.rc,
        "an unquota'd cgroup on a slim label must abort (output: %s)" % result.combined,
    )
    gate.assert_contains(result.combined, "HOST_LEAK", "names the failure mode")
    gate.assert_contains(result.combined, "memory ceiling", "names the memory number")
    gate.assert_contains(result.combined, "CPU quota", "names the cpu number")
    gate.assert_contains(
        sample.read_text(encoding="utf-8"),
        "HOST_LEAK",
        "writes a HOST_LEAK meta line for the panel",
    )

    # CONTROL: identical tree, non-slim label -> the leak check must not fire, because a 4-core VM legitimately reports 4 cores.
    control = harness.run(
        ["bash", str(SAMPLER), "--out", str(tmp_path / "ok.tsv"), "--interval", "1"],
        env={
            "PROFILER_CGROUP_ROOT": str(cgroup),
            "PROFILER_RUNNER_LABEL": "ubuntu-latest",
            "PROFILER_MAX_SECONDS": "1",
        },
        timeout=20,
    )
    gate.assert_exit_code(
        0,
        control.rc,
        "CONTROL: the same limits on ubuntu-latest are not a leak (output: %s)" % control.combined,
    )
    gate.log_pass("the sampler aborts on HOST_LEAK under a slim label and runs normally otherwise")


def test_sampler_produces_a_real_profile(gate, tmp_path):
    # End-to-end on THIS machine: prove the sampler writes a meta line and real, varying samples that the aggregator accepts. Without this the whole suite only proves the aggregator can read files this file wrote.
    if not SAMPLER.is_file():
        gate.log_fail("sampler not found at %s" % paths.relative_to_root(SAMPLER))
    sample = tmp_path / "s.tsv"
    run = harness.run(
        ["bash", str(SAMPLER), "--out", str(sample), "--interval", "1"],
        env={"PROFILER_RUNNER_LABEL": "selftest", "PROFILER_MAX_SECONDS": "6"},
        timeout=40,
    )
    gate.assert_exit_code(0, run.rc, "the sampler must exit cleanly on this machine")
    text = sample.read_text(encoding="utf-8")
    lines = len([line for line in text.splitlines() if line.startswith("S")])
    if lines < 4:
        gate.log_fail("expected at least 4 real samples in 6s at 1s, got %d" % lines)
    gate.assert_contains(text.splitlines()[0], "#META", "first line is the meta record")
    # STRICT on purpose. A healthy 6-second capture must not trip the starvation ratio: the first sample lands one interval IN, so a W-second run yields int(W/interval) samples and not one more. The off-by-one version of that arithmetic flagged this exact capture as "starved or died early", and a false alarm is how an anti-vacuity check ends up switched off.
    result = run_panel(gate, sample, 7, "true")
    gate.assert_exit_code(
        0,
        result.rc,
        "a healthy short capture must not trip the ratio (output: %s)" % result.combined,
    )
    gate.assert_contains(result.combined, "## Runner Profile", "a real capture renders a panel")
    gate.assert_contains(
        result.combined, "**Samples:** %d" % lines, "the panel counts every sample it was given"
    )
    gate.assert_not_contains(
        result.combined, "sample floor", "no starvation finding on a healthy capture"
    )
    gate.log_pass("a live 6-second capture produced %d samples and rendered" % lines)


def _live_memory_max() -> str:
    """This environment's own enforced memory ceiling, or "" when unconstrained."""
    try:
        value = pathlib.Path("/sys/fs/cgroup/memory.max").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not value or value == "max" or not value.isdigit():
        return ""
    return value


def test_sampler_reads_a_real_containers_ceiling(gate, tmp_path):
    # THE PREMISE THE WHOLE ADVISOR RESTS ON, proven against a real kernel rather than a fixture. Every other cgroup case in this file writes its own /sys/fs/cgroup files, so together they only prove the sampler can read files this file wrote. This one puts it inside a container the kernel is enforcing.
    #
    # Measured on this machine 2026-08-05, `docker run --memory=5g --cpus=1` reports
    # memory.max=5368709120 and cpu.max=100000 100000, while nproc says 20 and
    # MemTotal says ~57 GiB. That 20-vs-1 gap IS the failure mode.
    if not SAMPLER.is_file():
        gate.log_fail("sampler not found at %s" % paths.relative_to_root(SAMPLER))

    # NATIVE BRANCH FIRST, and it matters more than the docker one. If THIS environment is itself quota-constrained then it IS the container, and the premise can be proven directly against the kernel enforcing it. The docker branch is self-defeating in the success case: ubuntu-slim has no docker, so the day this suite moves to the runner the whole project aims at, the strongest
    # proof would silently become a SKIP.
    live_mem = _live_memory_max()
    if live_mem:
        native = tmp_path / "native.tsv"
        run = harness.run(
            ["bash", str(SAMPLER), "--out", str(native), "--interval", "1"],
            env={"PROFILER_RUNNER_LABEL": "selftest", "PROFILER_MAX_SECONDS": "3"},
            timeout=40,
        )
        gate.assert_exit_code(
            0, run.rc, "the sampler must run cleanly in this constrained environment"
        )
        meta = next(
            (
                line
                for line in native.read_text(encoding="utf-8").splitlines()
                if line.startswith("#META")
            ),
            "",
        )
        if not meta:
            gate.log_fail("no #META line written in a constrained environment")
        fields = meta.split("\t")
        tier = fields[1]
        ceiling = fields[3]
        if tier not in ("CGROUP_V2", "CGROUP_V1"):
            gate.log_fail(
                "a quota is enforced here (memory.max=%s) but the sampler resolved %r"
                % (live_mem, tier)
            )
        # The whole thesis in one assertion: when the kernel enforces a ceiling, the sampler reports THAT and never the machine behind it.
        if int(ceiling) != int(live_mem):
            gate.log_fail(
                "sampler reported %s but the enforced ceiling is %s (it read the host)"
                % (ceiling, live_mem)
            )
        gate.log_pass(
            "in this live cgroup-constrained environment the sampler reports the enforced "
            "ceiling (%s bytes), not the host's" % ceiling
        )
        return

    docker = shutil.which("docker")
    if not docker or harness.run([docker, "version"]).rc != 0:
        gate.log_pass(
            "SKIP: unconstrained environment and no docker, real-container ceiling unproven here"
        )
        return
    script = (
        "apk add --no-cache bash coreutils >/dev/null 2>&1;\n"
        "PROFILER_RUNNER_LABEL=ubuntu-slim PROFILER_MAX_SECONDS=3 "
        "bash /p/sampler-linux.sh --out /w/c.tsv --interval 1 2>&1;\n"
        "head -1 /w/c.tsv"
    )
    result = harness.run(
        [
            docker,
            "run",
            "--rm",
            "--memory=5g",
            "--cpus=1",
            "-v",
            "%s:/p:ro" % SAMPLER.parent,
            "-v",
            "%s:/w" % tmp_path,
            "--entrypoint",
            "sh",
            "alpine:latest",
            "-c",
            script,
        ],
        timeout=180,
    )
    if result.rc != 0:
        gate.log_pass(
            "SKIP: container run failed (rc=%d), ceiling unproven here: %s"
            % (result.rc, result.combined[:120])
        )
        return
    # PARSE THE FIELDS, do not substring-match the line. The first version of this
    # check globbed for *"cores=20"* | *"cores=1[0-9]"*, which could never fire for
    # two independent reasons: the brackets sit inside quotes so they are literal
    # text, and the meta line is TSV that contains no "cores=" anywhere. Three dead
    # arms reading as a passing host-leak guard is precisely the vacuous green this whole file exists to refuse.
    meta = next((line for line in result.combined.splitlines() if line.startswith("#META")), "")
    if not meta:
        gate.log_fail("no #META line came back from the container: %s" % result.combined[:300])
    fields = meta.split("\t")
    tier = fields[1]
    cpu_ceiling = int(fields[2])
    mem_ceiling = int(fields[3])
    # A cgroup tier is required: PROC_HOST here would mean it fell back to the very files that lie inside a container.
    if tier not in ("CGROUP_V2", "CGROUP_V1"):
        gate.log_fail(
            "expected a cgroup tier inside a real container, got %r (meta: %s)" % (tier, meta)
        )
    # Exactly one core and exactly 5 GiB are what docker was told to enforce.
    if not 900 <= cpu_ceiling <= 1100:
        gate.log_fail(
            "cpu ceiling %d millicores is not the container's 1000 (host would be 20000): %s"
            % (cpu_ceiling, meta)
        )
    if mem_ceiling != 5368709120:
        gate.log_fail(
            "memory ceiling %d is not the container's 5 GiB (host would be ~61e9): %s"
            % (mem_ceiling, meta)
        )
    gate.log_pass(
        "inside a real 1-core/5GiB container the sampler reads the CONTAINER's ceiling "
        "(%d millicores / %d bytes), not the host's" % (cpu_ceiling, mem_ceiling)
    )
