"""read_cap_seed: sampling, the stop rule and the summary line against the plan's own awk, and full runs on a fake rdc."""

from __future__ import annotations

import io
import json
import stat
import subprocess

import pytest

from rediacc_ci.ops import read_cap_seed as rcs

# PLAN-snapshot-read-io-cap.md, the L2 Accept's program, byte for byte.
L2_AWK = (
    r"""/^demo-heartbeat /{for(i=2;i<=NF;i++){split($i,a,"=");v[a[1]]=a[2]}} """
    r"""END{exit !(v["rc"]=="0" && v["peakload"]+0<=v["baseload"]+3.5 && v["peakwa"]+0<=15 && v["loadover8x3"]=="0")}"""
)
# The L3 Accept's program, as the replacement line in the report names it.
L3_AWK = (
    r"""{for(i=2;i<=NF;i++){split($i,a,"=");v[a[1]]=a[2]}} """
    r"""END{exit !(v["rc"]=="0" && v["cpuQuota"]=="400%" && v["backupcpun"]+0>0 && v["backupcpun"]==v["samples"] && v["backupcpuover50"]=="0")}"""
)
CONFIG = ["demo-heartbeat", "--machine", "hostinger", "--config", "eu-bench"]


def awk_rc(program, text):
    return subprocess.run(["awk", program], input=text, text=True, check=False).returncode


def fig(load=1.0, busy=20.0, iowait=1.0, backup=10.0):
    return rcs.Figures(load=load, busy=busy, iowait=iowait, backup=backup)


def record(**extra):
    base = {
        "status": "ok",
        "snapshotId": "20261105T000000Z-abc",
        "imageBytes": 2147483648,
        "cellBytes": 4194304,
        "chunksAsked": 100,
        "chunksSampled": 0,
        "rehashReason": "no journal: first backup of this repo here",
        "readCapBps": 50000000,
        "hashWorkers": 1,
        "cpuLimitPercent": 50,
        "cpuQuota": "400%",
        "bytesUploaded": 0,
        "durationMs": 10500,
    }
    return {**base, **extra}


def result(**extra):
    base = {
        "repo": "demo-heartbeat",
        "rc": 0,
        "snapshot_rc": 0,
        "baseload": 1.19,
        "figures": (fig(), fig(load=1.4), fig()),
        "record": record(),
    }
    return rcs.RunResult(**{**base, **extra})


# ---------------------------------------------------------------- sampling

SAMPLE_TEXT = """uptime 1000.00 7000.00
load 1.19 1.00 0.90 1/300 4242
cpu  100 0 100 700 50 0 0 50 10 0
nproc 8
scope /system.slice/run-r1.scope 5000000
"""


def test_parse_sample_reads_every_field():
    sample = rcs.parse_sample(SAMPLE_TEXT)
    assert sample == rcs.Sample(
        uptime=1000.0,
        load=1.19,
        cpu_total=1000,
        cpu_idle=700,
        cpu_iowait=50,
        cores=8,
        scopes={"/system.slice/run-r1.scope": 5000000},
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "uptime 1 2\nload 1 1 1\nnproc 8\n",
        SAMPLE_TEXT.replace("nproc 8", "nproc 0"),
        SAMPLE_TEXT.replace("load 1.19", "load x"),
        SAMPLE_TEXT.replace("cpu  100 0 100 700 50 0 0 50 10 0", "cpu 1 2 3"),
    ],
)
def test_parse_sample_refuses_a_partial_answer(text):
    assert rcs.parse_sample(text) is None


def test_the_sample_command_runs_on_a_real_shell_and_parses():
    """The real bytes: a quoting slip in SAMPLE_COMMAND shows here, and no fake output can show it."""
    proc = subprocess.run(
        ["bash", "-c", rcs.SAMPLE_COMMAND], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    sample = rcs.parse_sample(proc.stdout)
    assert sample is not None
    assert sample.cores >= 1
    assert sample.cpu_total > 0


def test_only_a_transient_scope_counts_as_the_backup():
    """A process with the verb's name outside `run-*.scope` (a login session, init.scope) is not the backup."""
    holder = subprocess.Popen(["bash", "-c", 'exec -a "renet backup snapshot --repo x" sleep 15'])
    try:
        proc = subprocess.run(
            ["bash", "-c", rcs.SAMPLE_COMMAND], capture_output=True, text=True, check=False
        )
    finally:
        holder.kill()
        holder.wait()
    assert proc.returncode == 0, proc.stderr
    parsed = rcs.parse_sample(proc.stdout)
    assert parsed is not None
    assert all("/run-" in path for path in parsed.scopes)


def test_the_sample_command_writes_nothing():
    assert ">" not in rcs.SAMPLE_COMMAND
    for word in ("rm ", "tee", "kill", "sudo", "docker"):
        assert word not in rcs.SAMPLE_COMMAND


def sample(uptime, total, idle, iowait, load=1.0, cores=8, scopes=None):
    return rcs.Sample(uptime, load, total, idle, iowait, cores, scopes or {})


def test_figures_are_deltas_and_busy_counts_iowait():
    prev = sample(100.0, 1000, 800, 10)
    cur = sample(110.0, 2000, 1500, 110, load=2.5)
    figure = rcs.interval_figures(prev, cur)
    assert figure is not None
    assert figure.load == 2.5
    assert figure.busy == pytest.approx(30.0)
    assert figure.iowait == pytest.approx(10.0)
    assert figure.backup is None


def test_backup_cpu_is_a_share_of_all_cores():
    prev = sample(100.0, 1000, 800, 0, scopes={"/s/a.scope": 1_000_000})
    # 40 core-seconds over 10 s on 8 cores: half of the machine.
    cur = sample(110.0, 2000, 1500, 0, scopes={"/s/a.scope": 41_000_000})
    figure = rcs.interval_figures(prev, cur)
    assert figure is not None
    assert figure.backup == pytest.approx(50.0)


def test_a_scope_born_inside_the_interval_counts_from_zero():
    prev = sample(100.0, 1000, 800, 0)
    cur = sample(110.0, 2000, 1500, 0, scopes={"/s/a.scope": 8_000_000})
    figure = rcs.interval_figures(prev, cur)
    assert figure is not None
    assert figure.backup == pytest.approx(10.0)


@pytest.mark.parametrize(
    "cur",
    [sample(100.0, 2000, 1500, 0), sample(110.0, 1000, 800, 0)],
)
def test_no_time_or_no_tick_gives_no_figure(cur):
    assert rcs.interval_figures(sample(100.0, 1000, 800, 0), cur) is None


# ---------------------------------------------------------------- the stop rule


def test_load_rule_is_at_or_above_for_three_in_a_row():
    at = fig(load=1.0 + 3.5)
    under = fig(load=4.49)
    assert rcs.rule_fired("load", [at, at, at], 1.0)
    assert not rcs.rule_fired("load", [at, at, under, at, at], 1.0)
    assert not rcs.rule_fired("load", [at, at], 1.0)
    assert rcs.rule_fired("load", [under, at, at, at, under], 1.0)


def test_cpu_rule_is_strictly_above_for_three_in_a_row():
    over = fig(busy=50.1)
    at = fig(busy=50.0)
    assert rcs.rule_fired("cpu", [over, over, over], 0.0)
    assert not rcs.rule_fired("cpu", [over, over, at], 0.0)


def test_rules_read_their_own_figure():
    busy_only = fig(load=0.1, busy=99.0)
    loaded_only = fig(load=99.0, busy=1.0)
    assert not rcs.rule_fired("load", [busy_only] * 3, 1.0)
    assert not rcs.rule_fired("cpu", [loaded_only] * 3, 1.0)


# ---------------------------------------------------------------- the summary line and the awks


def test_a_good_line_passes_the_l2_awk():
    line = rcs.summary_line(result())
    assert line.startswith(
        "demo-heartbeat rc=0 peakload=1.40 baseload=1.19 peakwa=1.00 loadover8x3=0 "
    )
    assert awk_rc(L2_AWK, line + "\n") == 0


def test_the_awk_refuses_a_missing_repository():
    assert awk_rc(L2_AWK, rcs.summary_line(result(repo="other")) + "\n") == 1


@pytest.mark.parametrize(
    "planted",
    [
        pytest.param(result(rc=1, snapshot_rc=1), id="snapshot-failed"),
        pytest.param(result(figures=(fig(load=4.70),) * 2), id="peak-over-baseload-plus-3.5"),
        pytest.param(result(figures=(fig(iowait=15.01),) * 3), id="iowait-over-15"),
        pytest.param(
            result(rc=rcs.EXIT_NO_SAMPLES, figures=()),
            id="no-samples",
        ),
        pytest.param(
            rcs.RunResult("demo-heartbeat", rcs.EXIT_NO_SAMPLES, None, None),
            id="no-baseline",
        ),
    ],
)
def test_a_planted_line_is_rejected_by_the_l2_awk(planted):
    assert awk_rc(L2_AWK, rcs.summary_line(planted) + "\n") == 1


def test_the_control_of_the_planted_set_passes_just_under_the_bound():
    # Without a passing neighbour, the planted set could fail for any reason.
    figures = (fig(load=4.68, iowait=15.0), fig(load=1.0), fig(load=4.68))
    assert awk_rc(L2_AWK, rcs.summary_line(result(figures=figures)) + "\n") == 0


def test_the_load_rule_field_alone_is_rejected_by_the_l2_awk():
    good = rcs.summary_line(result())
    assert " loadover8x3=0 " in good
    assert awk_rc(L2_AWK, good.replace(" loadover8x3=0 ", " loadover8x3=1 ") + "\n") == 1


def test_a_good_l3_line_passes_and_each_miss_is_rejected():
    assert awk_rc(L3_AWK, rcs.summary_line(result()) + "\n") == 0
    misses = [
        result(figures=(fig(), fig(backup=50.01), fig())),
        result(figures=(fig(), fig(backup=None), fig())),
        result(figures=(fig(backup=None),) * 3),
        result(record=record(cpuQuota="800%")),
        result(record=record(cpuQuota=None)),
        result(record=None),
        result(figures=()),
        result(rc=rcs.EXIT_STOPPED),
    ]
    for planted in misses:
        assert awk_rc(L3_AWK, rcs.summary_line(planted) + "\n") == 1, planted


def test_the_line_stays_one_field_per_value():
    line = rcs.summary_line(result(record=record(snapshotId="a b=c")))
    assert "\n" not in line
    assert " snapshotId=a_b_c " in line
    assert all("=" in token for token in line.split()[1:])


def test_per_sample_cpu_figures_are_on_the_line():
    line = rcs.summary_line(
        result(figures=(fig(backup=12.5, busy=20.0), fig(backup=None, busy=30.0)))
    )
    assert " backupcpu=12.50,none " in line
    assert line.endswith(" busycpu=20.00,30.00")
    assert " peakbackupcpu=12.50 " in line
    assert " backupcpun=1 " in line


# ---------------------------------------------------------------- read evidence


def test_a_rehash_is_read_evidence_even_when_only_samples_were_asked():
    evidence = rcs.read_evidence(record(chunksAsked=5, chunksSampled=5))
    assert evidence.kind == "full-rehash"


def test_changed_cells_count_beyond_the_sample():
    evidence = rcs.read_evidence(record(rehashReason="", chunksAsked=7, chunksSampled=5))
    assert evidence == rcs.ReadEvidence("changed-cells", 2 * 4194304)


def test_a_no_change_run_is_visibly_weak():
    line = rcs.summary_line(result(record=record(rehashReason="", chunksAsked=5, chunksSampled=5)))
    assert " readkind=no-change " in line
    assert " readbytes=0 " in line
    assert " weak=1 " in line
    assert " weakreason=no-change " in line


def test_no_record_and_few_samples_are_weak():
    assert rcs.weak_reasons(rcs.read_evidence(None), 2) == ["no-record", "few-samples"]
    assert rcs.weak_reasons(rcs.read_evidence(record()), 3) == []


def test_the_record_is_read_from_the_pretty_printed_envelope():
    noise = (
        "connecting\n" + json.dumps({"success": True, "data": record()}, indent=2) + "\ntrailer {\n"
    )
    parsed = rcs.parse_record(noise)
    assert parsed is not None
    assert parsed["snapshotId"] == "20261105T000000Z-abc"
    assert rcs.parse_record("no json at all") is None


def test_find_job_id_takes_the_live_ticket_of_this_repository_only():
    rows = [
        {"id": "gone", "verb": "backup snapshot", "repo": "demo-heartbeat", "machine": "hostinger", "state": "succeeded"},
        {"id": "other", "verb": "backup snapshot", "repo": "mail", "machine": "hostinger", "state": "running"},
        {"id": "wrong", "verb": "repo up", "repo": "demo-heartbeat", "machine": "hostinger", "state": "running"},
        {"id": "right", "verb": "backup snapshot", "repo": "demo-heartbeat:latest", "machine": "hostinger", "state": "running"},
    ]  # fmt: skip
    text = json.dumps({"success": True, "data": rows}, indent=2)
    assert rcs.find_job_id(text, "demo-heartbeat", "hostinger") == "right"
    assert rcs.find_job_id(text, "demo-heartbeat", "elsewhere") is None


# ---------------------------------------------------------------- the exit code


@pytest.mark.parametrize(
    ("snapshot_rc", "count", "stopped", "want"),
    [
        (0, 3, "none", 0),
        (7, 3, "none", 7),
        (0, 0, "none", rcs.EXIT_NO_SAMPLES),
        (7, 0, "none", 7),
        (0, 3, "load", rcs.EXIT_STOPPED),
        (143, 3, "load", 143),
    ],
)
def test_final_rc(snapshot_rc, count, stopped, want):
    assert rcs.final_rc(snapshot_rc, count, stopped) == want


# ---------------------------------------------------------------- full runs on a fake rdc


class FakeProc:
    """A snapshot client that exits on its `lives`-th wait, or on a cancel."""

    def __init__(self, world, lives, rc):
        self.world = world
        self.lives = lives
        self.rc = rc

    def wait(self, timeout=None):
        if self.world.cancelled or self.lives <= 0:
            return self.rc
        self.lives -= 1
        self.world.now += timeout or 0.0
        raise subprocess.TimeoutExpired("rdc", timeout)

    def send_signal(self, _sig):
        raise AssertionError("no detach expected")

    def kill(self):
        raise AssertionError("no kill expected")


class World:
    """The fake machine and rdc: `loads` is one load per sample read after the baseline."""

    def __init__(self, tmp_path, loads=(), lives=3, rc=0, sample_rc=0, rec=None, cancel_rc=0):
        self.now = 0.0
        self.tmp_path = tmp_path
        self.loads = list(loads)
        self.lives = lives
        self.rc = rc
        self.sample_rc = sample_rc
        self.rec = record() if rec is None else rec
        self.cancel_rc = cancel_rc
        self.cancelled = False
        self.calls = []
        self.spawned = None
        self.tick = 0
        self.snapshot_running = False

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def runner(self, argv, _timeout):
        self.calls.append(list(argv))
        verb = argv[argv.index("--config") + 2 :]
        if "connect" in verb:
            return self._sample()
        if "cancel" in verb:
            self.cancelled = self.cancel_rc == 0
            return self.cancel_rc, "", ""
        rows = [{"id": "job-1", "verb": "backup snapshot", "repo": "demo-heartbeat", "machine": "hostinger", "state": "running"}]  # fmt: skip
        return 0, json.dumps({"success": True, "data": rows}), ""

    def _sample(self):
        if self.sample_rc:
            return self.sample_rc, "", "ssh down\n"
        self.tick += 1
        load = self.loads.pop(0) if self.snapshot_running and self.loads else 1.0
        text = (
            "uptime %.1f 0\nload %.2f 1 1 1/1 1\ncpu  %d 0 0 %d 0 0 0 0 0 0\nnproc 8\n"
            "scope /system.slice/run-r1.scope %d\n"
        ) % (self.tick * 10.0, load, self.tick * 100, self.tick * 700, self.tick * 8_000_000)
        return 0, text, ""

    def spawner(self, argv, out_path, err_path):
        self.spawned = list(argv)
        self.snapshot_running = True
        out_path.write_text(json.dumps({"success": True, "data": self.rec}, indent=2))
        err_path.write_text("")
        return FakeProc(self, self.lives, self.rc)

    def main(self, *extra):
        out = io.StringIO()
        summary = self.tmp_path / "seed" / "summary.log"
        deps = rcs.Deps(
            runner=self.runner, spawner=self.spawner, clock=self.clock, sleep=self.sleep
        )
        rc = rcs.main([*CONFIG, "--summary", str(summary), *extra], deps=deps, out=out)
        return rc, out.getvalue(), summary


def test_a_clean_run_passes_the_awk_and_exits_zero(tmp_path):
    world = World(tmp_path, loads=[1.2, 1.3, 1.4])
    rc, out, summary = world.main()
    assert rc == 0
    line = summary.read_text()
    assert awk_rc(L2_AWK, line) == 0
    assert " samples=3 " in line
    assert " baseload=1.00 " in line
    assert " peakload=1.40 " in line
    assert " cpuQuota=400% " in line
    assert "read: at least" in out
    # 8 core-seconds per 10 s on 8 cores.
    assert " backupcpu=10.00,10.00,10.00 " in line


def test_no_samples_control_exits_non_zero_after_a_snapshot_that_passed(tmp_path):
    """The snapshot ends before the first sample: rc 0 from the verb must not read as a pass."""
    world = World(tmp_path, lives=0)
    rc, _, summary = world.main()
    assert rc == rcs.EXIT_NO_SAMPLES
    line = summary.read_text()
    assert " samples=0 " in line
    assert " snapshotrc=0 " in line
    assert awk_rc(L2_AWK, line) == 1


def test_no_baseline_never_starts_the_snapshot(tmp_path):
    world = World(tmp_path, sample_rc=255)
    rc, out, summary = world.main()
    assert rc == rcs.EXIT_NO_SAMPLES
    assert world.spawned is None
    assert "snapshot was not started" in out
    assert awk_rc(L2_AWK, summary.read_text()) == 1


def test_the_load_rule_cancels_the_job_and_the_exit_is_non_zero(tmp_path):
    world = World(tmp_path, loads=[9.0, 9.0, 9.0, 9.0], lives=10, rc=1)
    rc, out, summary = world.main()
    assert rc == 1
    assert [c for c in world.calls if "cancel" in c] == [
        ["./rdc.sh", "--config", "eu-bench", "-y", "job", "cancel", "job-1", "-m", "hostinger"]
    ]
    line = summary.read_text()
    assert " stopped=load " in line
    assert " cancelled=1 " in line
    assert " loadover8x3=1 " in line
    assert " samples=3 " in line
    assert "the load rule fired" in out
    assert awk_rc(L2_AWK, line) == 1


def test_a_rule_that_fired_is_never_a_pass_even_when_the_snapshot_committed(tmp_path):
    world = World(tmp_path, loads=[9.0, 9.0, 9.0], lives=10, rc=0)
    rc, _, summary = world.main()
    assert rc == rcs.EXIT_STOPPED
    assert " snapshotrc=0 " in summary.read_text()


def test_two_high_samples_do_not_stop(tmp_path):
    world = World(tmp_path, loads=[9.0, 9.0, 1.0], lives=3)
    rc, _, summary = world.main()
    assert rc == 0
    assert not [c for c in world.calls if "cancel" in c]
    assert " stopped=none " in summary.read_text()


def test_cpu_stop_rule_ignores_load(tmp_path):
    world = World(tmp_path, loads=[9.0, 9.0, 9.0], lives=3)
    rc, _, summary = world.main("--stop-on", "cpu")
    assert rc == 0
    line = summary.read_text()
    assert " stopped=none " in line
    assert " loadover8x3=1 " in line


def test_the_snapshot_rc_passes_through(tmp_path):
    rc, _, summary = World(tmp_path, loads=[1.0], lives=1, rc=7).main()
    assert rc == 7
    assert summary.read_text().startswith("demo-heartbeat rc=7 ")


def test_a_failed_cancel_is_retried_and_named(tmp_path):
    world = World(tmp_path, loads=[9.0] * 5, lives=5, rc=0, cancel_rc=1)
    rc, _, summary = world.main()
    assert rc == rcs.EXIT_STOPPED
    assert len([c for c in world.calls if "cancel" in c]) == 3
    assert " cancelled=0 " in summary.read_text()


def test_a_client_that_outlives_the_cancel_is_detached_not_left_hanging(tmp_path, monkeypatch):
    """The cancel landed but the follow never returns: SIGINT detaches it, and the run still ends non-zero."""

    signals: list[int] = []

    class Stuck(FakeProc):
        def wait(self, timeout=None):
            if signals:
                return 130
            self.world.now += timeout or 0.0
            raise subprocess.TimeoutExpired("rdc", timeout)

        def send_signal(self, sig):
            signals.append(sig)

    world = World(tmp_path, loads=[9.0] * 500)
    monkeypatch.setattr(world, "spawner", _stuck_spawner(world, Stuck))
    rc, _, summary = world.main()
    assert rc == 130
    assert signals == [rcs.signal.SIGINT]
    line = summary.read_text()
    assert " stopped=load " in line
    assert " cancelled=1 " in line


def _stuck_spawner(world, cls):
    def spawn(argv, out_path, err_path):
        world.spawned = list(argv)
        world.snapshot_running = True
        out_path.write_text("")
        err_path.write_text("")
        return cls(world, 0, 0)

    return spawn


def test_a_no_change_run_prints_that_it_read_nothing(tmp_path):
    rec = record(rehashReason="", chunksAsked=0, chunksSampled=0)
    rc, out, summary = World(tmp_path, loads=[1.0, 1.0, 1.0], rec=rec).main()
    assert rc == 0
    assert "NO BYTES SHOWN READ (no-change)" in out
    assert " weak=1 " in summary.read_text()


def test_each_run_appends_one_line(tmp_path):
    for _ in range(2):
        World(tmp_path, loads=[1.0, 1.0, 1.0]).main()
    lines = (tmp_path / "seed" / "summary.log").read_text().splitlines()
    assert len(lines) == 2


def test_only_the_named_verbs_ever_run_and_the_read_cap_stays_the_default(tmp_path):
    world = World(tmp_path, loads=[9.0, 9.0, 9.0, 9.0], lives=10, rc=1)
    world.main()
    assert world.spawned == [
        "./rdc.sh", "--config", "eu-bench", "-o", "json", "backup", "snapshot",
        "demo-heartbeat@hostinger", "--bwlimit", "100Mbps", "--parallelism", "2",
    ]  # fmt: skip
    verbs = set()
    for argv in world.calls:
        tail = [a for a in argv[3:] if a not in {"-o", "json", "-y"}]
        verbs.add(tuple(tail[:2]))
    assert verbs == {("term", "connect"), ("job", "list"), ("job", "cancel")}


@pytest.mark.parametrize(
    "argv",
    [
        ["demo-heartbeat", "--machine", "hostinger"],
        ["demo-heartbeat", "--config", "eu-bench"],
    ],
)
def test_config_and_machine_have_no_default(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        rcs.main(argv)
    assert exc.value.code == rcs.EXIT_USAGE
    capsys.readouterr()


@pytest.mark.parametrize(
    "argv",
    [
        ["bad name", "--machine", "m", "--config", "c"],
        ["r;rm", "--machine", "m", "--config", "c"],
        ["r", "--machine", "m m", "--config", "c"],
        ["r", "--machine", "m", "--config", "--x"],
    ],
)
def test_a_bad_name_starts_nothing(argv, tmp_path, capsys):
    world = World(tmp_path)
    deps = rcs.Deps(
        runner=world.runner, spawner=world.spawner, clock=world.clock, sleep=world.sleep
    )
    try:
        rc: object = rcs.main(
            [*argv, "--summary", str(tmp_path / "s.log")], deps=deps, out=io.StringIO()
        )
    except SystemExit as exc:
        rc = exc.code
    assert rc == rcs.EXIT_USAGE
    assert world.calls == []
    capsys.readouterr()


def test_an_unwritable_summary_starts_nothing(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    world = World(tmp_path)
    deps = rcs.Deps(
        runner=world.runner, spawner=world.spawner, clock=world.clock, sleep=world.sleep
    )
    rc = rcs.main([*CONFIG, "--summary", str(blocker / "s.log")], deps=deps, out=io.StringIO())
    assert rc == rcs.EXIT_USAGE
    assert world.calls == []


def test_the_real_subprocess_path_with_a_fake_rdc_script(tmp_path, monkeypatch):
    """Real Popen, real files, real sample command on this machine; only the verb is a script."""
    monkeypatch.setattr(rcs, "BASELINE_S", 0.2)
    monkeypatch.setattr(rcs, "INTERVAL_S", 0.2)
    script = tmp_path / "rdc"
    payload = json.dumps({"success": True, "data": record()}, indent=2)
    script.write_text(
        "#!/bin/bash\n"
        'if [ "$4" = connect ]; then exec bash -c "$7"; fi\n'
        "if [ \"$6\" = snapshot ]; then sleep 1; cat <<'JSON'\n" + payload + "\nJSON\nexit 0; fi\n"
        "exit 9\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    summary = tmp_path / "summary.log"
    out = io.StringIO()
    rc = rcs.main(
        [*CONFIG, "--rdc", str(script), "--summary", str(summary)],
        out=out,
    )
    assert rc == 0, out.getvalue()
    line = summary.read_text()
    assert line.startswith("demo-heartbeat rc=0 ")
    assert " snapshotId=20261105T000000Z-abc " in line
    assert (tmp_path / "summary.log.demo-heartbeat.out").read_text().strip() == payload
