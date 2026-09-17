"""Differential: `rediacc_ci.ci.profiler_sampler_linux` against its twin
`.ci/scripts/ci/profiler/sampler-linux.sh`.

FOUR LAYERS, because this pair has four genuinely different risks and only one of them is "does the output match".

  1. `--help` IS A SLICE OF THE SCRIPT'S OWN SOURCE. `usage()` is
     `sed -n '2,40p' "$0" | sed 's/^# \\?//'` (`sampler-linux.sh:80`), so the
     port carries the twin's 39 header lines verbatim and slices ITSELF. Two
     tests: the rendered text is byte-identical, and the carried block is
     byte-identical to the twin's, in both directions.
  2. THE ARGUMENT AND REFUSAL PATHS are deterministic and compared byte for
     byte on both streams -- including the one that never terminates.
  3. THE CGROUP TIERS are driven through `PROFILER_CGROUP_ROOT`, the twin's own
     declared test seam, over a fake cgroup tree per tier. This is where the
     port could silently read the host instead of the fixture, which is exactly
     the failure the twin exists to prevent.
  4. THE SAMPLE LOOP AND `--probe` carry live readings, so those are compared
     with the three genuinely time-varying fields normalized, and every
     normalization is named in the function that does it rather than applied by
     a blanket regex.

WHAT IS DELIBERATELY NOT COMPARED, and why each is a fact rather than a convenience:

  * `**bash:** ${BASH_VERSION:-unknown}`. The field asks which bash is running
    the sampler; in the port there is none, so it renders `unknown`. Forging the
    system bash's version would be a lie about the interpreter that produced the
    line. Nothing machine-reads it (grepped: the string appears only in the twin
    and this port), so the divergence is cosmetic and named.
  * `**Per-sample cost:**` and the two `df ... used` figures, which move between
    two consecutive runs of the SAME implementation.
  * The bash redirection diagnostics the twin emits for an unguarded
    `read < missing`, which carry the twin's own path and line number.

K=5 LEDGER: `.ci/shadow/w7p6-profiler-sampler.observations.jsonl`.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import time
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.ci import profiler_sampler_linux as port

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/ci/profiler/sampler-linux.sh"
PORT_REL = ".ci/rediacc_ci/ci/profiler_sampler_linux.py"
TWIN = ROOT / TWIN_REL
PORT = ROOT / PORT_REL

BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONPATH": str(ROOT / ".ci"),
}


def argv_for(side: str, script: pathlib.Path | None = None) -> list[str]:
    if side == "old":
        return ["bash", str(script or TWIN)]
    return ["python3", str(script or PORT)]


def run(
    side: str,
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    script: pathlib.Path | None = None,
    timeout: float = 60,
) -> tuple[int, str, str]:
    environ = dict(BASE_ENV)
    if env:
        environ.update(env)
    proc = subprocess.run(
        [*argv_for(side, script), *args],
        env=environ,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_both(
    args: list[str], *, env: dict[str, str] | None = None, timeout: float = 60
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    return run("old", args, env=env, timeout=timeout), run("new", args, env=env, timeout=timeout)


def assert_same(old: tuple[int, str, str], new: tuple[int, str, str]) -> None:
    assert new[0] == old[0], "exit: twin %s, port %s" % (old[0], new[0])
    assert new[1] == old[1], "stdout:\n--- twin\n%s--- port\n%s" % (old[1], new[1])
    assert new[2] == old[2], "stderr:\n--- twin\n%s--- port\n%s" % (old[2], new[2])


# --------------------------------------------------------------------------- Layer 1: --help is a slice of the file's own source ---------------------------------------------------------------------------


def _slice_2_40(path: pathlib.Path) -> str:
    """`sed -n '2,40p' <file> | sed 's/^# \\?//'`, in Python."""
    lines = path.read_text(encoding="utf-8").split("\n")
    return "\n".join(re.sub(r"^# ?", "", line) for line in lines[1:40])


def test_the_carried_header_block_is_byte_identical() -> None:
    """The port's lines 2-40 ARE the twin's lines 2-40, in both directions.

    This is the transcription check. If the twin's header is edited and the port is not, `--help` starts lying about the flags it accepts, and nothing else in this file would notice.
    """
    assert _slice_2_40(PORT) == _slice_2_40(TWIN)


def test_help_is_byte_identical() -> None:
    old, new = run_both(["--help"])
    assert old[0] == 0
    assert "PROFILER_CGROUP_ROOT" in old[1], "the usage text is empty; the slice is stale"
    assert_same(old, new)


def test_help_keeps_the_twins_dangling_backslash() -> None:
    """`sed -n '2,40p'` cuts the example mid-continuation; that is the twin's output.

    Line 41 (`--out /tmp/p.tsv --interval 2 &`) is outside the range, so the last line of `--help` ends in a bare `\\`. Tidying it in the port would make the two renderings differ, so it is pinned as a fact.
    """
    old, _ = run_both(["--help"])
    assert old[1].rstrip("\n").endswith("\\")


# --------------------------------------------------------------------------- Layer 2: arguments and refusals ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["--bogus"],
        ["-x"],
        ["--out", "/dev/null", "--interval", "0"],
        ["--out", "/dev/null", "--interval", "abc"],
        ["--out", "/dev/null", "--interval", "-1"],
        ["--out", "/dev/null", "--interval", "1.5"],
        ["--out", "/dev/null", "--interval", ""],
        # Dangling value flags. These SPUN FOREVER until 2026-09-10; see `test_a_dangling_value_flag_exits_on_both_sides` for the measurement.
        ["--out"],
        ["--interval"],
        ["--probe", "--out"],
        ["--out", "/dev/null", "--interval"],
        [],
    ],
)
def test_argument_refusals_are_byte_identical(args: list[str]) -> None:
    old, new = run_both(args, env={"PROFILER_RUNNER_LABEL": "x"})
    assert old[0] == 2, "expected a usage refusal, got %s" % (old,)
    assert_same(old, new)


def test_the_meta_record_carries_the_normalised_interval(tmp_path: pathlib.Path) -> None:
    """FIXED 2026-09-10 in BOTH SIDES. This test used to assert `01`.

    `01` is all digits, so `is_num` always accepted it, and the twin then echoed the RAW STRING into `#META` because it never converted `$INTERVAL` at all. The first version of this port stored `int(raw)` and wrote `1`; the differential caught that, reading the file did not. The twin now normalises with
    `INTERVAL=$((10#$INTERVAL))` -- the fix for the `08` death two cases down --
    which REASSIGNS the variable, so the raw string stops existing on that side and both records read `1`. The pair is still the point; only the value moved.
    """
    env = {
        "PROFILER_CGROUP_ROOT": str(_cgroup_v2(tmp_path)),
        "PROFILER_MAX_SECONDS": "0",  # exactly one tick; see `_sample_both`
        "PROFILER_RUNNER_LABEL": "x",
    }
    old = run("old", ["--out", str(tmp_path / "o.tsv"), "--interval", "01"], env=env, timeout=30)
    new = run("new", ["--out", str(tmp_path / "n.tsv"), "--interval", "01"], env=env, timeout=30)
    assert old[0] == new[0] == 0
    assert _meta(tmp_path / "o.tsv")[4] == "1", "the twin no longer normalises the interval"
    assert _meta(tmp_path / "n.tsv")[4] == "1"


def test_a_dangling_value_flag_exits_on_both_sides() -> None:
    """FIXED 2026-09-10 in BOTH SIDES. This test used to require a TIMEOUT to end.

    `sampler-linux.sh` did `OUT="${2:-}"; shift 2`. With the flag as the LAST
    argument, `shift 2` returns non-zero and shifts NOTHING, and `set -e` is deliberately off (`:54-57`), so `while (($# > 0))` never terminated. Measured then: `timeout 3` reported wall 3.01s, user 3.00s, cpu 100% -- one whole core, no output on either stream, no exit.

    Why it mattered more than its reachability suggested: the production caller (`.github/actions/profiler/index.js:117-123`) spawns the sampler `detached: true` and `child.unref()`s it, so nothing would have reaped the spin before GitHub's 6-hour job ceiling, and `PROFILER_MAX_SECONDS` could not help because it is evaluated inside a loop the spin never reached.

    Counted, not estimated: of the twin's 14 real invocation sites, TWELVE pass a value after the flag (`index.js:117`, `profiler-control.sh:121`, `test-profiler-report.sh:398,409,421,478,506`, `test_gate_profiler_report.py:548,568,592,656,703`) and TWO use `--probe` only (`profiler-probe.yml:54,72`), so ZERO were reachable -- it was one hand-typed invocation away and it failed
    silently, which is why it was worth fixing.

    THE TIMEOUT STAYS on `run`. It is now the control: if either side regresses to the spin, this fails as a TimeoutExpired rather than hanging the suite.
    """
    for flag in ("--out", "--interval"):
        old, new = run_both([flag], timeout=10)
        assert old[0] == 2, "the twin no longer refuses a dangling %s" % flag
        assert old[1] == "", "the twin printed to stdout"
        assert old[2] == "sampler-linux.sh: %s requires a value\n" % flag
        assert_same(old, new)


def test_probe_ignores_a_missing_out(tmp_path: pathlib.Path) -> None:
    """`--probe` returns before the `--out` requirement, on both sides."""
    env = {"PROFILER_CGROUP_ROOT": str(_cgroup_v2(tmp_path)), "PROFILER_RUNNER_LABEL": "x"}
    old, new = run_both(["--probe"], env=env)
    assert old[0] == new[0] == 0
    assert "--out <file>" not in old[2]


# --------------------------------------------------------------------------- Layer 3: the cgroup tiers, through the twin's own test seam ---------------------------------------------------------------------------


def _cgroup_v2(tmp_path: pathlib.Path, *, mem: str = "2147483648") -> pathlib.Path:
    cg = tmp_path / "cg-v2"
    cg.mkdir(exist_ok=True)
    (cg / "cpu.max").write_text("100000 100000\n", encoding="utf-8")
    (cg / "memory.max").write_text(mem + "\n", encoding="utf-8")
    (cg / "cpu.stat").write_text("usage_usec 123456\nuser_usec 1\n", encoding="utf-8")
    (cg / "memory.current").write_text("1048576\n", encoding="utf-8")
    (cg / "memory.stat").write_text("inactive_file 65536\nanon 1\n", encoding="utf-8")
    return cg


def _cgroup_v1(tmp_path: pathlib.Path) -> pathlib.Path:
    cg = tmp_path / "cg-v1"
    (cg / "cpu").mkdir(parents=True, exist_ok=True)
    (cg / "memory").mkdir(parents=True, exist_ok=True)
    (cg / "cpuacct").mkdir(parents=True, exist_ok=True)
    (cg / "cpu" / "cpu.cfs_quota_us").write_text("50000\n", encoding="utf-8")
    (cg / "cpu" / "cpu.cfs_period_us").write_text("100000\n", encoding="utf-8")
    (cg / "memory" / "memory.limit_in_bytes").write_text("1073741824\n", encoding="utf-8")
    (cg / "cpuacct" / "cpuacct.usage").write_text("600000000\n", encoding="utf-8")
    (cg / "memory" / "memory.usage_in_bytes").write_text("200000000\n", encoding="utf-8")
    (cg / "memory" / "memory.stat").write_text("total_inactive_file 1000\n", encoding="utf-8")
    return cg


def _meta(tsv: pathlib.Path) -> list[str]:
    head = tsv.read_text(encoding="utf-8").split("\n")[0]
    return head.split("\t")


def _rows(tsv: pathlib.Path) -> list[list[str]]:
    return [
        line.split("\t")
        for line in tsv.read_text(encoding="utf-8").split("\n")
        if line.startswith("S\t")
    ]


def _sample_both(
    tmp_path: pathlib.Path, cg: pathlib.Path, **extra: str
) -> tuple[tuple[int, str, str], tuple[int, str, str], pathlib.Path, pathlib.Path]:
    """One tick each, into SEPARATE files so neither run can read the other's.

    `PROFILER_MAX_SECONDS=0`, NOT 1, AND THAT IS A FIX FOR A RACE THIS FILE HIT.
    The stop test is `elapsed_s >= MAX_SECONDS` evaluated AFTER a row is written,
    so at 1 a first tick landing at 0.99s writes a SECOND row. Measured 16/16 single-row runs on an idle machine, and a 2-row run under the load of the full suite -- `row count: twin 1, port 2`, which reads exactly like a port defect and was the harness. At 0 the comparison is true at the first tick unconditionally, so both sides write exactly one row on any machine.
    """
    env = {
        "PROFILER_CGROUP_ROOT": str(cg),
        "PROFILER_MAX_SECONDS": "0",
        "PROFILER_RUNNER_LABEL": "x",
    }
    env.update(extra)
    out_old = tmp_path / "old.tsv"
    out_new = tmp_path / "new.tsv"
    old = run("old", ["--out", str(out_old), "--interval", "1"], env=env, timeout=45)
    new = run("new", ["--out", str(out_new), "--interval", "1"], env=env, timeout=45)
    return old, new, out_old, out_new


# Fields of the #META record that carry a live reading rather than a decision. Index 5 is start_ms. Everything else is a resolved constant and IS compared.
META_LIVE = {5}
# Fields of an S record that are live NO MATTER WHAT: 1 is t_ms, 4/5 are the
# interface byte counters, 6/7 are `df`.
SAMPLE_LIVE = {1, 4, 5, 6, 7}
# AND TWO MORE WHEN THE FIXTURE DOES NOT PIN THEM. On a PROC_HOST-tier fixture there is no `cpu.stat` and no `memory.current`, so columns 2 (cpu_milli) and 3 (mem_bytes) come from the real `/proc/stat` and `/proc/meminfo` and move between two consecutive runs. Treating them as fixed made three cases fail on a difference that was the machine, not the port -- which is why this is a
# parameter and not a constant.
PROC_HOST_LIVE = SAMPLE_LIVE | {2, 3}


def assert_meta_same(a: pathlib.Path, b: pathlib.Path) -> None:
    ma, mb = _meta(a), _meta(b)
    assert len(ma) == len(mb) == 11, "the #META record changed width: %s / %s" % (ma, mb)
    for i, (x, y) in enumerate(zip(ma, mb, strict=True)):
        if i in META_LIVE:
            continue
        assert x == y, "#META field %d: twin %r, port %r" % (i, x, y)


def assert_rows_same(a: pathlib.Path, b: pathlib.Path, live: set[int] = SAMPLE_LIVE) -> None:
    ra, rb = _rows(a), _rows(b)
    assert ra, "the twin wrote no sample row"
    assert rb, "the port wrote no sample row"
    assert len(ra) == len(rb), "row count: twin %d, port %d" % (len(ra), len(rb))
    # Anti-vacuity: with every column excused this helper asserts nothing.
    assert len(live) < 8, "no column is being compared"
    for n, (x, y) in enumerate(zip(ra, rb, strict=True)):
        assert len(x) == 8, "row %d changed width in the twin" % n
        assert len(y) == 8, "row %d changed width in the port" % n
        for i in range(8):
            if i in live:
                continue
            assert x[i] == y[i], "row %d field %d: twin %r, port %r" % (n, i, x[i], y[i])


def test_cgroup_v2_tier(tmp_path: pathlib.Path) -> None:
    old, new, a, b = _sample_both(tmp_path, _cgroup_v2(tmp_path))
    assert old[0] == new[0] == 0
    assert _meta(a)[1] == "CGROUP_V2"
    assert _meta(a)[2] == "1000", "1 core of quota"
    # memory.current minus inactive_file, exact on a static fixture.
    assert _rows(a)[0][3] == "983040"
    assert_meta_same(a, b)
    assert_rows_same(a, b)
    assert old[1] == new[1]


def test_cgroup_v1_tier(tmp_path: pathlib.Path) -> None:
    old, new, a, b = _sample_both(tmp_path, _cgroup_v1(tmp_path))
    assert old[0] == new[0] == 0
    assert _meta(a)[1] == "CGROUP_V1"
    assert _meta(a)[2] == "500", "half a core of quota"
    assert _rows(a)[0][3] == "199999000"
    assert_meta_same(a, b)
    assert_rows_same(a, b)


def test_proc_host_tier_when_the_cgroup_is_empty(tmp_path: pathlib.Path) -> None:
    cg = tmp_path / "cg-none"
    cg.mkdir()
    _old, _new, a, b = _sample_both(tmp_path, cg)
    assert _meta(a)[1] == "PROC_HOST"
    assert _meta(a)[7] == "PROC_HOST", "cpu_src"
    assert _meta(a)[8] == "PROC_HOST", "mem_src"
    assert_meta_same(a, b)
    assert_rows_same(a, b, live=PROC_HOST_LIVE)


def test_cpu_max_without_a_quota_is_a_host_reading(tmp_path: pathlib.Path) -> None:
    """`cpu.max` = "max 100000": the cgroup exists and imposes no quota.

    `CPU_MODE` stays V2 (so usage still comes from `cpu.stat`) while `CPU_SRC` falls to PROC_HOST, which is the pair of facts the twin's comment at `:154-156` describes and the one place the two variables disagree.
    """
    cg = tmp_path / "cg-max"
    cg.mkdir()
    (cg / "cpu.max").write_text("max 100000\n", encoding="utf-8")
    (cg / "cpu.stat").write_text("usage_usec 5\n", encoding="utf-8")
    _old, _new, a, b = _sample_both(tmp_path, cg)
    assert _meta(a)[7] == "PROC_HOST"
    assert_meta_same(a, b)
    assert_rows_same(a, b, live=PROC_HOST_LIVE)


def test_an_unterminated_cgroup_file_defeats_the_whole_branch(tmp_path: pathlib.Path) -> None:
    """`read` returns NON-ZERO without a trailing newline, so the `if` is false.

    `cpu.max` written as `100000 100000` with no `\\n` sends `detect_cpu_ceiling` past both cgroup branches to `nproc`, leaving `CPU_MODE` empty as well. This is the single behaviour of `read` most likely to be lost in a port, because `open().readline()` returns the same STRING and a different STATUS.
    """
    cg = tmp_path / "cg-nonl"
    cg.mkdir()
    (cg / "cpu.max").write_text("100000 100000", encoding="utf-8")  # no newline
    _old, _new, a, b = _sample_both(tmp_path, cg)
    assert _meta(a)[7] == "PROC_HOST", "the twin honoured an unterminated cpu.max"
    assert_meta_same(a, b)
    assert_rows_same(a, b, live=PROC_HOST_LIVE)


def test_host_leak_is_byte_identical(tmp_path: pathlib.Path) -> None:
    """The exit-3 path, and the one sample-mode case with NO live field at all."""
    cg = _cgroup_v2(tmp_path, mem="17179869184")
    env = {"PROFILER_CGROUP_ROOT": str(cg), "PROFILER_RUNNER_LABEL": "ubuntu-slim"}
    out_old = tmp_path / "leak-old.tsv"
    out_new = tmp_path / "leak-new.tsv"
    old = run("old", ["--out", str(out_old), "--interval", "1"], env=env, timeout=30)
    new = run("new", ["--out", str(out_new), "--interval", "1"], env=env, timeout=30)
    assert old[0] == 3, "HOST_LEAK must be exit 3"
    assert "HOST_LEAK on runner label 'ubuntu-slim'" in old[2]
    assert_same(old, new)
    assert out_old.read_text() == out_new.read_text()
    assert _meta(out_old)[1] == "HOST_LEAK"
    assert _meta(out_old)[5] == "0", "start_ms is a literal 0 on the leak record"


def test_a_slim_label_within_the_ceiling_does_not_leak(tmp_path: pathlib.Path) -> None:
    """NEGATIVE control: the same label, a believable cgroup, no refusal."""
    cg = _cgroup_v2(tmp_path)
    old, new, a, b = _sample_both(tmp_path, cg, PROFILER_RUNNER_LABEL="ubuntu-slim")
    assert old[0] == new[0] == 0
    assert "HOST_LEAK" not in old[2]
    assert_meta_same(a, b)


def test_runner_environment_is_rejected_whole_not_cleaned(tmp_path: pathlib.Path) -> None:
    """`case $RUNNER_ENV in '' | *[!a-z-]*)` (`:218-220`).

    An uppercase or underscored value becomes `unknown` ENTIRELY, rather than being stripped down to its acceptable characters. Both directions.
    """
    cg = _cgroup_v2(tmp_path)
    _o, _n, a, b = _sample_both(tmp_path, cg, RUNNER_ENVIRONMENT="Github-Hosted")
    assert _meta(a)[10] == "unknown"
    assert_meta_same(a, b)
    _o, _n, a2, b2 = _sample_both(tmp_path, cg, RUNNER_ENVIRONMENT="github-hosted")
    assert _meta(a2)[10] == "github-hosted"
    assert_meta_same(a2, b2)


def test_a_non_numeric_disk_cadence_falls_back_to_sixty(tmp_path: pathlib.Path) -> None:
    cg = _cgroup_v2(tmp_path)
    _o, _n, a, b = _sample_both(tmp_path, cg, PROFILER_DISK_EVERY_S="zzz")
    assert_meta_same(a, b)
    assert_rows_same(a, b)


def test_the_missing_memory_current_diagnostic_is_the_twins_alone(
    tmp_path: pathlib.Path,
) -> None:
    """A NAMED, DELIBERATELY-NOT-REPRODUCED DIVERGENCE, pinned as still real.

    `read_mem_bytes:314` guards `$CG/memory.current` with `[ "$MEM_MODE" = "V2" ]`
    and NOT with `-r`, so a tree with `memory.max` and no `memory.current` makes real bash write `<twin path>: line 314: <CG>/memory.current: No such file or directory` -- ONCE PER TICK, measured: 4 ticks produced exactly 4 lines. This port matches the DECISION (fall through) and does not forge a diagnostic carrying the twin's own path and line number.

    Unreachable in production: a real cgroup v2 tree always exposes both files, so this needs `PROFILER_CGROUP_ROOT`, which is a declared test seam.
    """
    cg = tmp_path / "cg-nocur"
    cg.mkdir()
    (cg / "memory.max").write_text("2147483648\n", encoding="utf-8")
    old, new, a, b = _sample_both(tmp_path, cg)
    assert "memory.current: No such file or directory" in old[2], (
        "the twin stopped emitting the diagnostic; this divergence is stale"
    )
    assert "memory.current" not in new[2], "the port started forging a bash diagnostic"
    assert old[0] == new[0] == 0
    assert_meta_same(a, b)
    assert_rows_same(a, b, live=PROC_HOST_LIVE)


@pytest.mark.parametrize("bad", ["08", "09"])
def test_an_octal_invalid_interval_now_runs_on_both_sides(tmp_path: pathlib.Path, bad: str) -> None:
    """FIXED 2026-09-10 in BOTH SIDES. This test used to assert the death.

    `DISK_EVERY=$(((DISK_EVERY_S + INTERVAL - 1) / INTERVAL))` and `$(( ))` reads a
    leading `0` as OCTAL. `08` and `09` are not valid octal, so bash refused the expression, left `DISK_EVERY` unassigned, and the next line expanded it into `set -u`. Measured:

        sampler-linux.sh: line 584: 08: value too great for base (error token is "08")
        sampler-linux.sh: line 585: DISK_EVERY: unbound variable
        rc=1, one #META line written, zero samples

    The `#META` record is written BEFORE that point, so the artefact a consumer picked up was a header with no body -- which `report.awk` reads as a profile
    that collected nothing rather than as a crash. `INTERVAL=$((10#$INTERVAL))`
    closes it; `#META` now records the normalised `8`.

    Blast radius: `.github/actions/profiler/action.yml:25` defaults `interval` to `'10'` and the three live callers of the composite (`profiler-probe.yml:89,108,127`) pass `'5'`, so zero were affected.
    """
    cg = _cgroup_v2(tmp_path)
    env = {
        "PROFILER_CGROUP_ROOT": str(cg),
        "PROFILER_MAX_SECONDS": "0",  # exactly one tick
        "PROFILER_RUNNER_LABEL": "x",
    }
    out_old = tmp_path / ("oct-old-%s.tsv" % bad)
    out_new = tmp_path / ("oct-new-%s.tsv" % bad)
    old = run("old", ["--out", str(out_old), "--interval", bad], env=env, timeout=30)
    new = run("new", ["--out", str(out_new), "--interval", bad], env=env, timeout=30)
    assert old[0] == 0, "the twin still dies on --interval %s:\n%s" % (bad, old[2])
    assert new[0] == 0, "the port still dies on --interval %s:\n%s" % (bad, new[2])
    assert "value too great for base" not in old[2]
    assert "unbound variable" not in old[2]
    assert _meta(out_old)[4] == bad.lstrip("0"), "the interval was not normalised"
    assert len(_rows(out_old)) >= 1, "no sample row was written"
    assert_meta_same(out_old, out_new)
    assert_rows_same(out_old, out_new)


@pytest.mark.parametrize("bad", ["08", "09"])
def test_an_octal_invalid_disk_cadence_now_runs_on_both_sides(
    tmp_path: pathlib.Path, bad: str
) -> None:
    """THE SIBLING OF THE CASE ABOVE, found on 2026-09-10 by sweeping for it.

    `PROFILER_DISK_EVERY_S` is guarded by `is_num "$X" && [ "$X" -ge 1 ]`, and BOTH halves say yes to `08`: it is all digits, and `test` parses base 10. So `08` reached the same `$(( ))` one line further on and produced the same two
    diagnostics and the same rc=1, from a knob whose guard looks like it validates.
    Fixing only `--interval` would have left this open, which is why the sweep happened before the fix was called done.
    """
    cg = _cgroup_v2(tmp_path)
    _o, _n, a, b = _sample_both(tmp_path, cg, PROFILER_DISK_EVERY_S=bad)
    assert _o[0] == 0, "the twin still dies on PROFILER_DISK_EVERY_S=%s:\n%s" % (bad, _o[2])
    assert _n[0] == 0, "the port still dies on PROFILER_DISK_EVERY_S=%s:\n%s" % (bad, _n[2])
    assert "value too great for base" not in _o[2]
    assert_meta_same(a, b)
    assert_rows_same(a, b)


def test_a_valid_octal_interval_is_now_one_number(tmp_path: pathlib.Path) -> None:
    """FIXED 2026-09-10. `010` used to be three numbers in one run.

    `$((010))` is 8, so the disk-decimation divisor was 8; `read -t 010` waits 10 real seconds (measured on a fifo: 10.01s); `[ 010 -lt 1 ]` reads decimal 10; and the `#META` record said `010`. One flag, four readings, three values. The quiet half of the `08` case, and the reason the fix normalises rather than merely rejecting a leading zero: `010` never errored, it just meant
    different things in different lines. It is `10` everywhere now.

    `_arith` stays and is driven directly here: it is still the correct model of `$(( ))`, and it is what makes the normalisation a choice rather than an accident of Python's `int()`.
    """
    cg = _cgroup_v2(tmp_path)
    env = {
        "PROFILER_CGROUP_ROOT": str(cg),
        "PROFILER_MAX_SECONDS": "0",  # exactly one tick
        "PROFILER_RUNNER_LABEL": "x",
    }
    out_old = tmp_path / "o010.tsv"
    out_new = tmp_path / "n010.tsv"
    old = run("old", ["--out", str(out_old), "--interval", "010"], env=env, timeout=45)
    new = run("new", ["--out", str(out_new), "--interval", "010"], env=env, timeout=45)
    assert old[0] == new[0] == 0
    assert _meta(out_old)[4] == _meta(out_new)[4] == "10"
    assert_meta_same(out_old, out_new)
    assert_rows_same(out_old, out_new)
    # The arithmetic half, driven directly rather than inferred from the TSV. This is what `10#` is protecting against, and it has not changed.
    assert port._arith("010") == 8
    assert port._arith("10") == 10
    with pytest.raises(port.BashArithError):
        port._arith("08")


@pytest.mark.parametrize("bad", ["abc", "10s", "-1", "1.5", "6h", " 5", "0x10"])
def test_a_non_numeric_max_seconds_is_refused_at_startup(tmp_path: pathlib.Path, bad: str) -> None:
    """FIXED 2026-09-10 in BOTH SIDES. This test used to require BOTH to be killed.

    The only use was `[ <elapsed> -ge "$MAX_SECONDS" ]`, and `test` prints `[: abc: integer expected` and evaluates FALSE on a non-numeric operand. So
    `PROFILER_MAX_SECONDS=abc` did not clamp the sampler to some default -- it
    removed the self-termination ENTIRELY, on a process the production caller detaches and unrefs. Measured: 3 ticks in 4 seconds, three diagnostics, no stop, killed by `timeout`. The old version of this test asserted exactly that, and a port that stopped on its own would have been the safer program and the wrong port; the fix had to land on both sides at once for that reason.

    REJECTED, not coerced to the 6-hour default: this file has both conventions (`--interval` refuses, `PROFILER_DISK_EVERY_S` falls back silently) and the line between them is what a wrong value costs. A wrong `df` cadence costs a sampling rate; a wrong max-seconds costs a sampler running forever.

    NOT in the matrix: `""`. `${VAR:-default}` treats exported-empty as UNSET, so an
    empty value is the 21600 default and not a refusal at all;
    `test_an_empty_max_seconds_is_the_default_not_a_refusal` is that control, and it is separate because driving it here would mean waiting out a six-hour default.
    """
    cg = _cgroup_v2(tmp_path)
    env = {
        "PROFILER_CGROUP_ROOT": str(cg),
        "PROFILER_MAX_SECONDS": bad,
        "PROFILER_RUNNER_LABEL": "x",
    }
    out_old = tmp_path / "ms-old.tsv"
    out_new = tmp_path / "ms-new.tsv"
    old = run("old", ["--out", str(out_old), "--interval", "1"], env=env, timeout=10)
    new = run("new", ["--out", str(out_new), "--interval", "1"], env=env, timeout=10)
    assert old[0] == 2, "the twin accepted PROFILER_MAX_SECONDS=%r" % bad
    assert old[1] == ""
    assert old[2] == (
        "sampler-linux.sh: PROFILER_MAX_SECONDS must be a whole number of seconds, got '%s'\n" % bad
    )
    assert not out_old.exists(), "the twin wrote an artefact before refusing"
    assert_same(old, new)


def test_an_empty_max_seconds_is_the_default_not_a_refusal(tmp_path: pathlib.Path) -> None:
    """THE NEGATIVE CONTROL for the refusal above, and for `${VAR:-default}`.

    An exported-but-EMPTY value is UNSET to `:-`, so it is the 21600 default and must NOT be refused. Driven through `--probe`, which returns before any sampling: the refusal is checked at startup, so if empty were being rejected the probe would exit 2 here instead of printing its report. Sampling it directly would mean waiting out six hours to prove a negative.
    """
    env = {
        "PROFILER_CGROUP_ROOT": str(_cgroup_v2(tmp_path)),
        "PROFILER_MAX_SECONDS": "",
        "PROFILER_RUNNER_LABEL": "x",
    }
    old, new = run_both(["--probe"], env=env, timeout=30)
    # NOT `assert_same`: a probe report carries the three live readings this file declares uncomparable (bash version, both `df ... used` figures, per-sample cost). `test_probe_agrees_on_everything_that_is_not_a_live_reading` owns that comparison; the subject here is only that neither side refuses.
    for side, r in (("twin", old), ("port", new)):
        assert r[0] == 0, "%s refused an empty PROFILER_MAX_SECONDS:\n%s" % (side, r[2])
        assert "PROFILER_MAX_SECONDS" not in r[2]
        assert "## Runner probe: x" in r[1]


def test_a_non_numeric_max_seconds_is_refused_in_probe_mode_too(
    tmp_path: pathlib.Path,
) -> None:
    """Deliberate: `--probe` answers "will the sampler work on this runner".

    The knob is validated BEFORE the `--probe` branch, so a value that would stop the sampler cannot pass quietly through the very command that exists to say so.
    """
    env = {
        "PROFILER_CGROUP_ROOT": str(_cgroup_v2(tmp_path)),
        "PROFILER_MAX_SECONDS": "abc",
        "PROFILER_RUNNER_LABEL": "x",
    }
    old, new = run_both(["--probe"], env=env, timeout=30)
    assert old[0] == 2
    assert "PROFILER_MAX_SECONDS must be a whole number of seconds" in old[2]
    assert old[1] == "", "the probe report was printed anyway"
    assert_same(old, new)


def test_a_leading_zero_max_seconds_is_read_in_base_ten(tmp_path: pathlib.Path) -> None:
    """`010` was octal 8 to `$(( ))` and decimal 10 to `test`; now it is 10 to both.

    Driven at `00`, which is 0 either way, so the guard fires on the first tick and the message reports the NORMALISED value -- the same reassignment the interval gets, and the reason both sides print `0` rather than `00`.
    """
    cg = _cgroup_v2(tmp_path)
    env = {
        "PROFILER_CGROUP_ROOT": str(cg),
        "PROFILER_MAX_SECONDS": "00",
        "PROFILER_RUNNER_LABEL": "x",
    }
    old = run("old", ["--out", str(tmp_path / "z-old.tsv"), "--interval", "1"], env=env, timeout=30)
    new = run("new", ["--out", str(tmp_path / "z-new.tsv"), "--interval", "1"], env=env, timeout=30)
    assert old[0] == new[0] == 0
    assert "reached PROFILER_MAX_SECONDS=0, stopping" in old[2]
    assert_same(old, new)


def test_a_numeric_max_seconds_does_stop_the_loop(tmp_path: pathlib.Path) -> None:
    """The control for the case above: the guard works when `test` can read it."""
    cg = _cgroup_v2(tmp_path)
    old, new, _a, _b = _sample_both(tmp_path, cg)
    assert old[0] == new[0] == 0
    assert "reached PROFILER_MAX_SECONDS=0, stopping" in old[2]
    assert "reached PROFILER_MAX_SECONDS=0, stopping" in new[2]


def test_max_seconds_stops_the_loop_and_says_so(tmp_path: pathlib.Path) -> None:
    cg = _cgroup_v2(tmp_path)
    old, new, _a, _b = _sample_both(tmp_path, cg)
    assert "reached PROFILER_MAX_SECONDS=0, stopping" in old[2]
    assert_same((old[0], old[1], old[2]), (new[0], new[1], new[2]))


# --------------------------------------------------------------------------- Layer 4: --probe and the sample loop's live readings ---------------------------------------------------------------------------

# The three lines whose value legitimately differs between two consecutive runs of the SAME implementation, plus the one that describes the interpreter.
PROBE_VOLATILE = (
    "**Per-sample cost:**",
    "**df workspace used:**",
    "**df runner temp used:**",
    "**bash:**",
)


def _probe_stable(text: str) -> str:
    out = []
    for line in text.split("\n"):
        head = next((p for p in PROBE_VOLATILE if line.startswith(p)), None)
        out.append(head or line)
    return "\n".join(out)


def test_probe_agrees_on_everything_that_is_not_a_live_reading(
    tmp_path: pathlib.Path,
) -> None:
    cg = _cgroup_v2(tmp_path)
    env = {"PROFILER_CGROUP_ROOT": str(cg), "PROFILER_RUNNER_LABEL": "self"}
    old, new = run_both(["--probe"], env=env)
    assert old[0] == new[0] == 0
    assert old[2] == new[2] == ""
    stable_old, stable_new = _probe_stable(old[1]), _probe_stable(new[1])
    assert stable_old == stable_new, "probe:\n--- twin\n%s--- port\n%s" % (old[1], new[1])
    # Anti-vacuity for the normalization: the four volatile lines must EXIST, or `_probe_stable` is folding nothing and this test compares two constants.
    for marker in PROBE_VOLATILE:
        assert marker in old[1], "the twin no longer prints %s" % marker
    assert stable_old.count("\n") > 20, "the probe collapsed to a handful of lines"


def test_probe_reports_the_host_leak_without_failing(tmp_path: pathlib.Path) -> None:
    """`--probe` NAMES the leak and still exits 0; only sample mode refuses."""
    cg = _cgroup_v2(tmp_path, mem="17179869184")
    env = {"PROFILER_CGROUP_ROOT": str(cg), "PROFILER_RUNNER_LABEL": "ubuntu-slim"}
    old, new = run_both(["--probe"], env=env)
    assert old[0] == new[0] == 0
    assert "**Host leak check:** WOULD FAIL - HOST_LEAK" in old[1]
    assert _probe_stable(old[1]) == _probe_stable(new[1])


def test_probe_tees_into_the_step_summary(tmp_path: pathlib.Path) -> None:
    """`run_probe | tee -a "$GITHUB_STEP_SUMMARY"`: stdout AND the file, appended."""
    cg = _cgroup_v2(tmp_path)
    results = {}
    for side in ("old", "new"):
        summary = tmp_path / ("summary-%s.md" % side)
        summary.write_text("PRE-EXISTING\n", encoding="utf-8")
        rc, out, err = run(
            side,
            ["--probe"],
            env={
                "PROFILER_CGROUP_ROOT": str(cg),
                "PROFILER_RUNNER_LABEL": "x",
                "GITHUB_STEP_SUMMARY": str(summary),
            },
        )
        assert rc == 0
        assert err == ""
        body = summary.read_text(encoding="utf-8")
        assert body.startswith("PRE-EXISTING\n"), "%s truncated the summary" % side
        results[side] = (_probe_stable(out), _probe_stable(body))
    assert results["old"] == results["new"]


def test_sigterm_latency_matches_the_twin(tmp_path: pathlib.Path) -> None:
    """bash DEFERS the trap until `read -t` times out, and so must the port.

    THIS TEST EXISTS BECAUSE THE FIRST VERSION OF THE PORT GOT IT BACKWARDS. It used `signal.set_wakeup_fd` to make `select` return the instant a SIGTERM arrived, on the assumption that bash's `read -t` does the same. Measured at `--interval 5` with the signal 1.2s in: twin 3.80s, port 0.043s. bash waits out the remaining interval. That is not cosmetic -- the production stopper
    (`.github/actions/profiler/index.js:148-166`) SIGTERMs, waits, then SIGKILLs and annotates the panel with "the sampler had to be SIGKILLed", so a faster port would silently change which note a job's panel carries.

    The assertion is a RELATIVE one against the twin measured in the same run, not an absolute number, because the absolute is a property of the machine.
    """
    cg = _cgroup_v2(tmp_path)
    interval = 5
    delay = 1.0
    latency = {}
    for side in ("old", "new"):
        proc = subprocess.Popen(
            [
                *argv_for(side),
                "--out",
                str(tmp_path / ("t-%s.tsv" % side)),
                "--interval",
                str(interval),
            ],
            env={**BASE_ENV, "PROFILER_CGROUP_ROOT": str(cg), "PROFILER_RUNNER_LABEL": "x"},
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(delay)
        start = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=interval + 20) == 0
        latency[side] = time.monotonic() - start

    expected = interval - delay
    assert latency["old"] > expected * 0.5, (
        "the twin died in %.2fs; it is supposed to wait out the interval" % latency["old"]
    )
    assert abs(latency["new"] - latency["old"]) < 1.5, (
        "SIGTERM latency: twin %.2fs, port %.2fs -- the port must not die sooner"
        % (latency["old"], latency["new"])
    )


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", True),
        ("01", True),
        ("123456789012345678901234567890", True),
        ("", False),
        (None, False),
        ("-1", False),
        ("+1", False),
        ("1.0", False),
        (" 1", False),
        ("1 ", False),
        ("max", False),
        ("1e3", False),
    ],
)
def test_is_num_matches_the_bash_case_statement(value: str | None, expected: bool) -> None:
    assert port.is_num(value) is expected


def test_is_num_agrees_with_real_bash() -> None:
    """The helper against the real `case` it reproduces, not against a table.

    A table only proves the table. This drives `is_num`'s own body out of the twin under a real bash, over the same inputs.
    """
    probe = (
        "is_num() { case \"${1:-}\" in '' | *[!0-9]*) return 1 ;; *) return 0 ;; esac; }\n"
        'for v in "$@"; do if is_num "$v"; then echo 1; else echo 0; fi; done\n'
    )
    values = ["0", "01", "", "-1", "+1", "1.0", " 1", "max", "9" * 30]
    proc = subprocess.run(
        ["bash", "-c", probe, "bash", *values],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    answers = proc.stdout.split()
    assert len(answers) == len(values)
    for value, answer in zip(values, answers, strict=True):
        assert port.is_num(value) is (answer == "1"), "is_num(%r)" % value


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [(7, 2, 3), (-7, 2, -3), (7, -2, -3), (-7, -2, 3), (0, 5, 0)],
)
def test_idiv_truncates_toward_zero(a: int, b: int, expected: int) -> None:
    """`$(( ))` truncates; Python's `//` floors. `-7 // 2` is -4, not -3."""
    assert port._idiv(a, b) == expected


def test_split_fields_gives_the_remainder_to_the_last_name() -> None:
    assert port._split_fields("a b c d", 2) == ["a", "b c d"]
    assert port._split_fields("  a   b  ", 2) == ["a", "b"]
    assert port._split_fields("a", 3) == ["a", "", ""]
    assert port._split_fields("  spaced  out  ", 1) == ["spaced  out"]


def test_read_fields_reports_an_unterminated_line_as_a_failure(
    tmp_path: pathlib.Path,
) -> None:
    good = tmp_path / "good"
    good.write_text("100000 100000\n", encoding="utf-8")
    assert port._read_fields(str(good), 2) == (True, ["100000", "100000"])
    bad = tmp_path / "bad"
    bad.write_text("100000 100000", encoding="utf-8")
    assert port._read_fields(str(bad), 2) == (False, ["100000", "100000"])
    empty = tmp_path / "empty"
    empty.write_text("", encoding="utf-8")
    assert port._read_fields(str(empty), 1) == (False, [""])


def test_iter_fields_drops_an_unterminated_final_line(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "f"
    path.write_text("a 1\nb 2\nc 3", encoding="utf-8")
    assert list(port._iter_fields(str(path), 2)) == [["a", "1"], ["b", "2"]]


def test_read_fields_matches_real_bash_on_the_status(tmp_path: pathlib.Path) -> None:
    """The `ok` flag against real `read`, because it decides a whole branch."""
    for body, expected in (("x\n", 0), ("x", 1), ("", 1)):
        path = tmp_path / "probe"
        path.write_text(body, encoding="utf-8")
        proc = subprocess.run(
            ["bash", "-c", 'read -r v < "$1"; echo $?', "bash", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert proc.stdout.strip() == str(expected)
        ok, _fields = port._read_fields(str(path), 1)
        assert ok is (expected == 0), "body=%r" % body


# --------------------------------------------------------------------------- A PLANTED DEFECT, on a throwaway copy, never on the file on disk ---------------------------------------------------------------------------


def _planted_copy(tmp_path: pathlib.Path, old: str, new: str) -> pathlib.Path:
    source = PORT.read_text(encoding="utf-8")
    assert source.count(old) == 1, "the plant anchor moved: %r" % old[:60]
    copy = tmp_path / "planted.py"
    copy.write_text(source.replace(old, new, 1), encoding="utf-8")
    return copy


def test_a_planted_missing_inactive_file_subtraction_is_caught(
    tmp_path: pathlib.Path,
) -> None:
    """Report `memory.current` raw instead of minus `inactive_file`.

    The tidiest-looking wrong change here: page cache counted as usage inflates every memory reading, and on a clean runner the two numbers are close enough that nobody would notice by eye. On the static fixture they are 1048576 and 983040.
    """
    before = PORT.read_bytes()
    copy = _planted_copy(
        tmp_path,
        "                c, i = int(cur), int(inactive)\n"
        "                self.mem_bytes = c - i if c > i else c\n"
        "                return True\n"
        '        if self.mem_mode == "V1":',
        "                self.mem_bytes = int(cur)\n"
        "                return True\n"
        '        if self.mem_mode == "V1":',
    )
    cg = _cgroup_v2(tmp_path)
    env = {
        "PROFILER_CGROUP_ROOT": str(cg),
        "PROFILER_MAX_SECONDS": "0",  # exactly one tick
        "PROFILER_RUNNER_LABEL": "x",
    }
    out_old = tmp_path / "p-old.tsv"
    out_new = tmp_path / "p-new.tsv"
    run("old", ["--out", str(out_old), "--interval", "1"], env=env, timeout=45)
    run("new", ["--out", str(out_new), "--interval", "1"], env=env, script=copy, timeout=45)
    assert _rows(out_old)[0][3] == "983040", "the control is broken: the twin's value moved"
    assert _rows(out_new)[0][3] == "1048576", "the plant did not change the port's reading"
    assert hashlib.sha256(before).hexdigest() == hashlib.sha256(PORT.read_bytes()).hexdigest()


def test_a_planted_regression_of_the_dangling_flag_guard_is_caught(
    tmp_path: pathlib.Path,
) -> None:
    """Plant the OLD defect back into the port and prove the comparison sees it.

    Until 2026-09-10 this ran the other way round: it planted the obvious REPAIR (refuse `--out` with no value) into a port that had to reproduce a twin which spun. The bug is fixed in both sides now, so the tempting change is the reverse one -- dropping the arity check back to `args[1] if len(args) > 1 else ""` -- and that is what is planted. Either way the claim is the same: a
    port may reword, never change what it does.

    The plant is a SPIN, so the port copy is run under a short timeout and the TimeoutExpired IS the assertion.
    """
    before = PORT.read_bytes()
    guard = (
        "                if len(args) < 2:\n"
        '                    print("sampler-linux.sh: --out requires a value", file=sys.stderr, flush=True)\n'
        "                    return 2\n"
        "                self.out = args[1]\n"
    )
    regressed = (
        '                self.out = args[1] if len(args) > 1 else ""\n'
        "                while len(args) < 2:\n"
        "                    pass\n"
    )
    copy = _planted_copy(tmp_path, guard, regressed)
    old = run("old", ["--out"], timeout=10)
    assert old[0] == 2, "the control is broken: the twin no longer refuses"
    with pytest.raises(subprocess.TimeoutExpired):
        run("new", ["--out"], script=copy, timeout=4)
    assert hashlib.sha256(before).hexdigest() == hashlib.sha256(PORT.read_bytes()).hexdigest()


def test_the_port_file_on_disk_is_untouched_by_this_module() -> None:
    """A last, cheap guard: the two plants above are the only mutations here.

    Runs last by name ordering only as a courtesy; the real protection is the hash assertion inside each plant. This one catches an EDIT made by a future
    case that forgets to copy first.
    """
    text = PORT.read_text(encoding="utf-8")
    assert 'print("sampler-linux.sh: --out requires a value"' in text, (
        "the dangling-flag guard was removed from the real port file"
    )
    assert "self.mem_bytes = c - i if c > i else c" in text, (
        "the inactive_file subtraction was removed from the real port file"
    )


def test_the_module_is_executable() -> None:
    """The twin is path-invoked (`bash <path>`), so the port carries the bit too."""
    assert os.access(PORT, os.X_OK)
    assert PORT.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n")
    assert shutil.which("bash"), "the differential needs a real bash"
