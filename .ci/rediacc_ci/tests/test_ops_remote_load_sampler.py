"""remote_load_sampler: phases, peaks and exit codes on a fake runner, a fake clock and a fake command."""

from __future__ import annotations

import io
import subprocess

from rediacc_ci.ops import remote_load_sampler as rls


class World:
    """A fake clock, a scripted machine and a command that exits after `run_s` seconds."""

    def __init__(self, loads, iowait_share=0.0, run_s=30.0, cmd_rc=0, fail_from=None):
        self.now, self.loads, self.iowait_share = 0.0, list(loads), iowait_share
        self.run_s, self.cmd_rc, self.fail_from = run_s, cmd_rc, fail_from
        self.calls, self.started = 0, None

    def clock(self):
        return self.now

    def sleep(self, s):
        self.now += s

    def runner(self, argv, timeout):
        assert argv[1:4] == ["--config", "eu-bench", "term"]
        self.calls += 1
        if self.fail_from is not None and self.calls >= self.fail_from:
            return 255, "", "ssh down"
        load = self.loads[min(self.calls - 1, len(self.loads) - 1)]
        ticks = int(self.now * 100)
        wa = int(ticks * self.iowait_share)
        text = "uptime %.2f 0\nload %.2f 0 0 0/0 0\ncpu 0 0 0 %d %d 0 0 0\nnproc 4\n" % (
            self.now + 100,
            load,
            ticks - wa,
            wa,
        )
        return 0, text, ""

    def spawner(self, argv):
        self.started = self.now
        world = self

        class Proc:
            def wait(self, timeout=None):
                world.now += timeout
                if world.now - world.started >= world.run_s:
                    return world.cmd_rc
                raise subprocess.TimeoutExpired("cmd", timeout)

        return Proc()

    def deps(self):
        return rls.Deps(runner=self.runner, spawner=self.spawner, clock=self.clock, sleep=self.sleep)


def drive(world, extra=()):
    out = io.StringIO()
    argv = [
        "--machine", "hostinger", "--config", "eu-bench",
        "--baseline-s", "20", "--after-s", "20", "--interval-s", "10",
        *extra, "--", "true",
    ]
    return rls.main(argv, world.deps(), out), out.getvalue()


def test_quiet_run_exits_zero_and_reports_every_phase():
    code, text = drive(World([1.0]))
    assert code == 0
    line = text.strip().splitlines()[-1]
    assert "baseload=1.00" in line and "peakload=1.00" in line and "rc=0" in line
    assert text.count("baseline load=") == 3 and "during load=" in text and "after load=" in text


def test_control_load_over_threshold_exits_nonzero():
    # Three baseline samples read 1.0, then the load jumps to 9.0 once the command runs.
    code, text = drive(World([1.0, 1.0, 1.0, 9.0, 9.0, 9.0, 9.0, 9.0]))
    assert code == rls.EXIT_THRESHOLD
    assert "peak_load_9.00_exceeds_baseline_1.00" in text


def test_control_iowait_over_threshold_exits_nonzero():
    code, text = drive(World([1.0], iowait_share=0.4))
    assert code == rls.EXIT_THRESHOLD and "peak_iowait" in text


def test_thresholds_off_when_negative():
    world = World([1.0, 1.0, 1.0, 9.0, 9.0, 9.0], iowait_share=0.4)
    code, _ = drive(world, ["--max-load-delta", "-1", "--max-iowait", "-1"])
    assert code == 0


def test_no_baseline_sample_exits_three():
    code, text = drive(World([1.0], fail_from=1))
    assert code == rls.EXIT_SAMPLING and "no_baseline_sample" in text


def test_unreadable_sample_midrun_exits_three():
    code, _ = drive(World([1.0], fail_from=4))
    assert code == rls.EXIT_SAMPLING


def test_command_rc_is_propagated():
    code, text = drive(World([1.0], cmd_rc=7))
    assert code == 7 and "cmdrc=7" in text


def test_duration_mode_without_command():
    out = io.StringIO()
    argv = [
        "--machine", "hostinger", "--config", "eu-bench",
        "--baseline-s", "10", "--after-s", "0", "--duration-s", "20",
    ]
    code = rls.main(argv, World([1.0]).deps(), out)
    assert code == 0 and "cmdrc=none" in out.getvalue()


def test_bad_arguments_exit_two():
    out = io.StringIO()
    assert rls.main(["--machine", "x y", "--config", "eu-bench", "--", "true"], World([1.0]).deps(), out) == 2
    assert rls.main(["--machine", "m", "--config", "c"], World([1.0]).deps(), out) == 2
