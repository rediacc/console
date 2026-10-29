"""job_latency with a fake rdc: recorded durations, a failing run, --compare, the one-run control."""

from __future__ import annotations

import io
import json
import stat

import pytest

from rediacc_ci.ops import job_latency as jl


class FakeClock:
    """Each runner call advances the clock by the next recorded duration (seconds)."""

    def __init__(self, durations):
        self.durations = list(durations)
        self.now = 0.0
        self.calls = 0

    def __call__(self):
        return self.now

    def runner(self, rc_by_run=None, stdout=""):
        def run(argv):
            self.last_argv = list(argv)
            self.now += self.durations[self.calls]
            self.calls += 1
            rc = (rc_by_run or {}).get(self.calls, 0)
            return rc, stdout.format(n=self.calls), "boom\n" if rc else ""

        return run


def _main(argv, clock, **kw):
    out = io.StringIO()
    rc = jl.main(argv, runner=clock.runner(**kw), clock=clock, out=out)
    return rc, out.getvalue()


BASE = ["--rdc", "./rdc.sh", "--config", "eu-bench"]


def test_percentiles_from_recorded_durations(tmp_path):
    clock = FakeClock([n / 1000.0 for n in range(1, 21)])
    target = tmp_path / "r.json"
    rc, out = _main([*BASE, "--runs", "20", "--out", str(target), "repo", "list"], clock)
    assert rc == 0
    assert "runs=20 p50_ms=10.0 p95_ms=19.0 max_ms=20.0" in out
    assert clock.last_argv == ["./rdc.sh", "--config", "eu-bench", "repo", "list"]
    saved = json.loads(target.read_text())
    assert saved["wall"] == pytest.approx({"p50": 10.0, "p95": 19.0, "max": 20.0})
    assert len(saved["wall_ms"]) == 20


def test_nonzero_rc_in_any_run_exits_2(tmp_path, capsys):
    clock = FakeClock([0.01] * 5)
    target = tmp_path / "r.json"
    rc, out = _main([*BASE, "--runs", "5", "--out", str(target), "x"], clock, rc_by_run={3: 7})
    assert rc == 2
    assert out == ""
    assert not target.exists()
    assert "run 3 of 5 exited 7: boom" in capsys.readouterr().err


def test_compare_prints_delta(tmp_path):
    def write(name, p50, p95, mx, start=None):
        data = {"runs": 1, "wall": {"p50": p50, "p95": p95, "max": mx}}
        if start:
            data["start_latency"] = start
        path = tmp_path / name
        path.write_text(json.dumps(data))
        return str(path)

    before = write("b.json", 100.0, 200.0, 300.0, {"p50": 5.0, "p95": 6.0, "max": 7.0})
    after = write("a.json", 130.0, 190.0, 300.0, {"p50": 9.0, "p95": 6.0, "max": 8.0})
    rc, out = _main(["--compare", before, after], FakeClock([]))
    assert rc == 0
    assert "wall.p50 before_ms=100.0 after_ms=130.0 delta_ms=+30.0" in out
    assert "wall.p95 before_ms=200.0 after_ms=190.0 delta_ms=-10.0" in out
    assert "start_latency.p50 before_ms=5.0 after_ms=9.0 delta_ms=+4.0" in out


def test_compare_missing_file_exits_2(tmp_path):
    rc, _ = _main(["--compare", str(tmp_path / "no"), str(tmp_path / "no2")], FakeClock([]))
    assert rc == 2


def test_control_one_run_one_sample():
    clock = FakeClock([0.25])
    rc, out = _main([*BASE, "--runs", "1", "x"], clock)
    assert rc == 0
    assert out.strip() == "runs=1 p50_ms=250.0 p95_ms=250.0 max_ms=250.0"
    assert "start_latency" not in out


def test_debug_collects_start_latency():
    clock = FakeClock([0.01] * 4)
    rc, out = _main(
        [*BASE, "--runs", "4", "--debug", "x"],
        clock,
        stdout="span rediacc.job.start_latency_ms={n}0.5\n",
    )
    assert rc == 0
    assert "--debug" in clock.last_argv
    assert "start_latency_ms samples=4 p50_ms=20.5 p95_ms=40.5 max_ms=40.5" in out


def test_no_debug_ignores_start_latency_lines():
    clock = FakeClock([0.01] * 2)
    rc, out = _main([*BASE, "--runs", "2", "x"], clock, stdout="rediacc.job.start_latency_ms=5.0\n")
    assert rc == 0
    assert "start_latency" not in out
    assert "--debug" not in clock.last_argv


def test_compare_missing_start_latency_key_exits_2(tmp_path, capsys):
    wall = {"p50": 1.0, "p95": 2.0, "max": 3.0}
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"wall": wall, "start_latency": wall}))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"wall": wall, "start_latency": {"p50": 1.0}}))
    rc, out = _main(["--compare", str(good), str(bad)], FakeClock([]))
    assert rc == 2
    assert out == ""
    assert "cannot read result file" in capsys.readouterr().err


def test_unwritable_out_exits_2_without_traceback(tmp_path, capsys):
    target = tmp_path / "no-such-dir" / "r.json"
    rc, out = _main([*BASE, "--runs", "1", "--out", str(target), "x"], FakeClock([0.1]))
    assert rc == 2
    assert out == ""
    assert "cannot write" in capsys.readouterr().err


def test_real_subprocess_fake_rdc(tmp_path):
    script = tmp_path / "rdc"
    script.write_text('#!/bin/sh\necho "rediacc.job.start_latency_ms: 12.5" >&2\nexit 0\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    out = io.StringIO()
    rc = jl.main(["--rdc", str(script), "--config", "c", "--runs", "2", "--debug", "x"], out=out)
    assert rc == 0
    assert "start_latency_ms samples=2 p50_ms=12.5" in out.getvalue()


def test_bad_arguments_exit_2():
    assert jl.main(["--rdc", "x"], out=io.StringIO()) == 2
