"""`rediacc_ci.ci.profiler_control`, the port of the retired `.ci/scripts/test/profiler-control.sh`.

The control itself takes about three minutes of real load, so it is never run here. What is tested is everything that decides its verdict: argument handling, the phase evaluation (the bash's awk program) over synthetic samples, and which sampler it runs.
"""

from __future__ import annotations

from rediacc_ci import paths
from rediacc_ci.ci import profiler_control as pc

ROOT = paths.repo_root()

MARKS = [
    ("BUSY", 10_000, 40_000),
    ("IDLE", 40_000, 70_000),
    ("ALLOC", 70_000, 100_000),
    ("DISK", 100_000, 175_000),
]


def _samples(
    tier: str,
    *,
    busy: float = 1000.0,
    idle: float = 50.0,
    alloc_mib: float = 512.0,
    disk_mib: float = 1024.0,
) -> list[str]:
    """One `S` row per second across the four phases, millicores and bytes as the sampler writes them."""
    rows = ["#META\t%s\t1000\t2147483648" % tier]
    base_mem = 100.0 * 1048576
    base_ws = 2_000_000.0
    for second in range(176):
        ms = second * 1000
        cpu, mem, ws = idle, base_mem, base_ws
        if 10_000 <= ms <= 40_000:
            cpu = busy + idle
        elif 70_000 <= ms <= 100_000:
            mem = base_mem + alloc_mib * 1048576
        elif ms >= 100_000:
            ws = base_ws + disk_mib * 1024
        rows.append("S\t%d\t%s\t%d\t0\t0\t%d" % (ms, cpu, int(mem), int(ws)))
    return rows


def test_the_sampler_it_runs_is_the_one_ci_runs() -> None:
    assert pc.SAMPLER == ROOT / ".ci" / "rediacc_ci" / "ci" / "profiler_sampler_linux.py"
    assert pc.SAMPLER.is_file()


def test_a_missing_sampler_is_a_setup_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(pc, "SAMPLER", ROOT / "no-such-sampler.py")
    assert pc.main([]) == 2
    assert "sampler not found" in capsys.readouterr().err


def test_arguments() -> None:
    assert pc.parse_args([]) == (2, False)
    assert pc.parse_args(["--interval", "5", "--keep"]) == (5, True)
    assert pc.parse_args(["--interval"]) == 2, "the flag as the last word must exit, never spin"
    assert pc.parse_args(["--interval", "abc"]) == 2
    assert pc.parse_args(["--bogus"]) == 2


def test_help_exits_zero(capsys) -> None:
    assert pc.parse_args(["--help"]) == 0
    assert "Exit: 0 every judged phase" in capsys.readouterr().out


def test_a_healthy_cgroup_run_passes_all_four() -> None:
    rc, report = pc.evaluate(_samples("CGROUP_V2"), MARKS, 2)
    assert rc == 0, report
    assert [line.split(" ", 2)[:2] for line in report[:4]] == [
        ["PASS", "BUSY:"],
        ["PASS", "IDLE:"],
        ["PASS", "ALLOC:"],
        ["PASS", "DISK:"],
    ]


def test_a_sampler_that_returns_a_constant_fails() -> None:
    """The control's reason to exist: a broken sampler fails every phase, not one."""
    rc, report = pc.evaluate(_samples("CGROUP_V2", busy=0.0, alloc_mib=0.0, disk_mib=0.0), MARKS, 2)
    assert rc == 1
    assert sum(line.startswith("FAIL") for line in report) == 3


def test_proc_host_is_inconclusive_not_green() -> None:
    rc, report = pc.evaluate(_samples("PROC_HOST"), MARKS, 2)
    assert rc == 2
    assert sum(line.startswith("SKIP") for line in report) == 3
    assert any(line.startswith("PASS DISK") for line in report), (
        "disk keeps its verdict at every tier"
    )
    assert any("CONTROL INCONCLUSIVE" in line for line in report)


def test_too_few_samples_is_a_failure() -> None:
    rc, report = pc.evaluate(_samples("CGROUP_V2")[:5], MARKS, 2)
    assert rc == 1
    assert report == ["FAIL setup: only 4 samples collected"]
