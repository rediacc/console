#!/usr/bin/env python3
"""Controls for the host-temp finished marker and the Stop segment `host-temp` (agent/plans/PLAN-host-temp-disposal.md HT11, HT13, D6, D7).

    python3 .claude/hooks/stop/test-hosttemp.py
    PYTHONPATH=.claude/hooks/stop python3 -m pytest -q .claude/hooks/stop/test-hosttemp.py -k marker

Every case works in its own temporary fixture repository and never touches a real path. Runs under pytest (the `test_` functions) and as a script (the `__main__` block runs each of them).
"""

import contextlib
import importlib
import importlib.util
import json
import math
import os
import pathlib
import statistics
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
AGENT = "a0123456789abcdef"


def _check(cond):
    """A failed control: raised, so it fails under pytest and the script alike."""
    if not cond:
        raise AssertionError("control failed")


def _mod(name):
    """A hook module by name. The hooks import each other flat, and both routes in the module docstring already put this directory on sys.path: a by-path run as sys.path[0], the pytest form through PYTHONPATH."""
    return importlib.import_module(name)


def _fixture(tmp, record=True):
    """A git repository whose common dir holds a lease record for AGENT (or none)."""
    root = pathlib.Path(tmp) / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    records = root / ".git" / _mod("wl_worktrees").RECORD_DIR
    records.mkdir()
    if record:
        (records / ("agent-%s.json" % AGENT)).write_text(json.dumps({"id": "agent-" + AGENT}))
    return root, records


def _marker(records):
    return records / ("agent-%s.finished" % AGENT)


def test_marker_final_stop_writes_it():
    wt = _mod("wl_worktrees")
    with tempfile.TemporaryDirectory() as tmp:
        root, records = _fixture(tmp)
        got = wt.mark_finished(root, AGENT, "/x/agent.jsonl", "", now=1000)
        body = json.loads(_marker(records).read_text())
        _check(got == str(_marker(records)))
        _check(body == {"agent": AGENT, "finished_at": 1000, "transcript": "/x/agent.jsonl"})
        wt.mark_finished(root, AGENT, "/x/agent.jsonl", "", now=2000)
        _check(json.loads(_marker(records).read_text())["finished_at"] == 2000)
        _check([p.name for p in records.iterdir() if p.suffix == ".tmp"] == [])


def test_marker_interim_stop_writes_none():
    wt = _mod("wl_worktrees")
    with tempfile.TemporaryDirectory() as tmp:
        root, records = _fixture(tmp)
        _check(wt.mark_finished(root, AGENT, "/x/agent.jsonl", "Monitor armed") == "")
        _check(not _marker(records).exists())


def test_marker_agent_without_record_writes_none():
    wt = _mod("wl_worktrees")
    with tempfile.TemporaryDirectory() as tmp:
        root, records = _fixture(tmp, record=False)
        _check(wt.mark_finished(root, AGENT, "/x/agent.jsonl", "") == "")
        _check(not _marker(records).exists())


def test_marker_unwritable_records_dir_raises_nothing():
    """A marker write that fails answers "" and leaves no temp file. The failure is planted as a non-empty directory where the marker goes, which `os.replace` refuses for root too, so the case asserts under every uid (review f2b58581.2: a 0o500 mode let root write and the case returned unasserted)."""
    wt = _mod("wl_worktrees")
    with tempfile.TemporaryDirectory() as tmp:
        root, records = _fixture(tmp)
        _marker(records).mkdir()
        (_marker(records) / "keep").write_text("x")
        _check(wt.mark_finished(root, AGENT, "/x/agent.jsonl", "") == "")
        _check(_marker(records).is_dir())
        _check([p.name for p in records.iterdir() if p.suffix == ".tmp"] == [])


def test_marker_written_by_the_subagent_stop_handler():
    report = _mod("wl_report")
    with tempfile.TemporaryDirectory() as tmp:
        root, records = _fixture(tmp)
        keys = ("CLAUDE_PROJECT_DIR", "WORKLIST_REPORTS_DIR")
        before = dict(os.environ)
        os.environ["CLAUDE_PROJECT_DIR"] = str(root)
        os.environ["WORKLIST_REPORTS_DIR"] = str(pathlib.Path(tmp) / "reports")
        real = report.armed_monitors
        try:
            event = {"agent_id": AGENT, "last_assistant_message": "done", "session_id": "s" * 8}
            report.handle_subagent_stop(event)
            _check(_marker(records).is_file())
            # an armed Monitor makes the stop interim: the rewrite must not happen
            _marker(records).unlink()
            transcript = pathlib.Path(tmp) / "agent.jsonl"
            transcript.write_text("{}\n")
            report.armed_monitors = lambda *_a, **_k: ["Monitor until x"]
            report.handle_subagent_stop({**event, "agent_transcript_path": str(transcript)})
            _check(not _marker(records).exists())
        finally:
            report.armed_monitors = real
            for key in keys:
                if key in before:
                    os.environ[key] = before[key]
                else:
                    os.environ.pop(key, None)


# ---- the Stop segment `host-temp` (HT13) -------------------------------------

NOW = 2_000_000.0


class _Popen:
    """A stand-in for subprocess.Popen that records each start; `pid` is this test's own pid, so the handed-over lock names a live process."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        return type("P", (), {"pid": os.getpid()})()


def _forbid_subprocess():
    """Make every subprocess entry point raise; returns the restore callable."""
    names = ("Popen", "run", "call", "check_call", "check_output")
    saved = {n: getattr(subprocess, n) for n in names}
    saved_system = os.system

    def boom(*_a, **_k):
        raise AssertionError("assess made a subprocess call")

    for name in names:
        setattr(subprocess, name, boom)
    os.system = boom

    def restore():
        for name, fn in saved.items():
            setattr(subprocess, name, fn)
        os.system = saved_system

    return restore


def _ht_fixture(tmp, leases=1, finished_ago=31 * 60, quiet_ago=None, sweeper=True):
    """A main checkout (a plain `.git` directory, as the hook reads it) with `leases` lease records and markers."""
    ht = _mod("wl_hosttemp")
    root = pathlib.Path(tmp) / "main"
    records = root / ".git" / ht.RECORD_DIR
    records.mkdir(parents=True)
    if sweeper:
        (root / ht.SWEEPER_REL).parent.mkdir(parents=True)
        (root / ht.SWEEPER_REL).write_text("")
    quiet_ago = finished_ago if quiet_ago is None else quiet_ago
    for i in range(leases):
        lease = "agent-%016x" % i
        transcript = pathlib.Path(tmp) / ("%s.jsonl" % lease)
        transcript.write_text("{}\n")
        os.utime(transcript, (NOW - quiet_ago, NOW - quiet_ago))
        (records / (lease + ".json")).write_text(json.dumps({"id": lease}))
        body = {
            "agent": lease[6:],
            "finished_at": NOW - finished_ago,
            "transcript": str(transcript),
        }
        (records / (lease + ht.MARKER_SUFFIX)).write_text(json.dumps(body))
    return ht, root, records


def _rows(records, *texts, ts=NOW):
    path = records / "sweeps.jsonl"
    seq = len(path.read_text().splitlines()) if path.exists() else 0
    with open(path, "a") as fh:
        for text in texts:
            seq += 1
            fh.write(json.dumps({"seq": seq, "ts": ts, "text": text}) + "\n")


def _last(ht, records, at):
    (records / ht.LAST_NAME).write_text(json.dumps({"at": at}))


def test_hosttemp_assess_fifteen_leases_no_subprocess_under_150ms():
    with tempfile.TemporaryDirectory() as tmp:
        ht, root, records = _ht_fixture(tmp, leases=15, finished_ago=10 * 60)
        _last(ht, records, NOW - 20 * 60)
        _rows(records, *["removed tree agent-%d (1.0 GB)" % i for i in range(40)], ts=NOW - 30)
        restore = _forbid_subprocess()
        times = []
        try:
            for _ in range(20):
                t0 = time.perf_counter()
                got = ht.assess(root, {}, now=NOW, popen=_Popen())
                times.append((time.perf_counter() - t0) * 1000.0)
        finally:
            restore()
        _check(got["due"] is False and got["why"] == "nothing ripe")
        _check(got["print"][0].startswith("host-temp: removed tree agent-0"))
        # The docstring's budget is 150 ms at p95, so the tail is held, not only the median (review 2872d8fe.4).
        _check(statistics.median(times) < 150.0)
        _check(_p95(times) < 150.0)


def _p95(times):
    """The 95th percentile of `times` by nearest rank: the smallest sample at or above 95% of them, never interpolated toward the slowest. Of 20 samples that is the 19th, so one scheduler stall on a loaded runner (the top 5%) cannot fail the budget, while a slow tail of two or more still does (review 64c46214.1: the interpolated cut moved 5% of the way to the slowest sample, and a single 3 s stall added 150 ms)."""
    ranked = sorted(times)
    return ranked[max(math.ceil(0.95 * len(ranked)) - 1, 0)]


def test_hosttemp_control_p95_catches_a_slow_tail_the_median_passes():
    tail = [5.0] * 17 + [400.0] * 3
    _check(statistics.median(tail) < 150.0)
    _check(_p95(tail) >= 150.0)
    _check(_p95([5.0] * 18 + [400.0] * 2) >= 150.0)


def test_hosttemp_control_p95_holds_through_one_stall():
    """One stall in 20 samples is the 5% tail the budget excludes, so the p95 stays at the fast samples."""
    _check(_p95([5.0] * 19 + [3000.0]) < 150.0)


def test_hosttemp_a_clock_stepped_back_still_sweeps_a_ripe_lease():
    """`sweep.last` two hours ahead of now (the clock stepped back): the distance counts either way, so a ripe marker starts a sweep."""
    with tempfile.TemporaryDirectory() as tmp:
        ht, root, records = _ht_fixture(tmp)
        _last(ht, records, NOW + 2 * 60 * 60)
        popen = _Popen()
        got = ht.assess(root, {}, now=NOW, popen=popen)
        _check(got["due"] and got["spawned"] and len(popen.calls) == 1)


def test_hosttemp_a_clock_stepped_back_runs_the_hourly_host_sweep():
    with tempfile.TemporaryDirectory() as tmp:
        ht, root, records = _ht_fixture(tmp, leases=0)
        _last(ht, records, NOW + 2 * 60 * 60)
        got = ht.assess(root, {}, now=NOW, popen=_Popen())
        _check(got["due"] and got["why"].startswith("no host sweep for 120 min"))


def test_hosttemp_control_a_clock_stepped_back_inside_the_retry_window_waits():
    with tempfile.TemporaryDirectory() as tmp:
        ht, root, records = _ht_fixture(tmp)
        _last(ht, records, NOW + 60)
        popen = _Popen()
        got = ht.assess(root, {}, now=NOW, popen=popen)
        _check(not got["due"] and got["why"].startswith("a sweeper started") and not popen.calls)


def test_hosttemp_due_sweep_starts_one_detached_sweeper_and_a_second_stop_none():
    with tempfile.TemporaryDirectory() as tmp:
        ht, root, records = _ht_fixture(tmp, leases=15)
        popen = _Popen()
        restore = _forbid_subprocess()
        try:
            first = ht.assess(root, {}, now=NOW, popen=popen)
            second = ht.assess(root, {}, now=NOW + 1, popen=popen)
        finally:
            restore()
        _check(first["due"] and first["spawned"])
        _check(len(popen.calls) == 1)
        argv, kw = popen.calls[0]
        _check(
            argv[-5:] == ["rediacc_ci.dev.host_temp", "--root", str(root), "sweep", "--lock-held"]
        )
        _check(kw.get("start_new_session") is True and kw.get("cwd") == str(root))
        lock = json.loads((records / ht.LOCK_NAME).read_text())
        _check(lock["pid"] == os.getpid() and lock["token"] == kw["env"][ht.LOCK_HANDOFF_ENV])
        _check(not second["spawned"] and second["why"] == "a sweeper is running")


def test_hosttemp_control_a_dead_sweeper_lock_is_taken_over_after_the_retry_window():
    with tempfile.TemporaryDirectory() as tmp:
        ht, root, records = _ht_fixture(tmp)
        dead = subprocess.Popen(["true"])
        dead.wait()
        lock = {"pid": dead.pid, "start": 1, "token": "x"}
        (records / ht.LOCK_NAME).write_text(json.dumps(lock))
        _last(ht, records, NOW - ht.RETRY_S - 1)
        popen = _Popen()
        got = ht.assess(root, {}, now=NOW, popen=popen)
        _check(got["spawned"] and len(popen.calls) == 1)
        (records / ht.LOCK_NAME).unlink()
        recent = ht.assess(root, {}, now=NOW + 1, popen=popen)
        _check(not recent["spawned"] and recent["why"].startswith("a sweeper started"))


def test_hosttemp_nothing_ripe_starts_nothing():
    for finished_ago, quiet_ago in ((29 * 60, None), (31 * 60, 10 * 60)):
        with tempfile.TemporaryDirectory() as tmp:
            ht, root, records = _ht_fixture(tmp, finished_ago=finished_ago, quiet_ago=quiet_ago)
            _last(ht, records, NOW - 20 * 60)
            popen = _Popen()
            got = ht.assess(root, {}, now=NOW, popen=popen)
            _check(not got["due"] and popen.calls == [])


def test_hosttemp_unreadable_transcript_never_ripens_a_marker():
    with tempfile.TemporaryDirectory() as tmp:
        ht, _root, records = _ht_fixture(tmp)
        _check(ht.ripe_since(records, NOW) > 0.0)
        marker = next(records.glob("*" + ht.MARKER_SUFFIX))
        body = json.loads(marker.read_text())
        body["transcript"] = body["transcript"] + "/not-a-dir"
        marker.write_text(json.dumps(body))
        _check(ht.ripe_since(records, NOW) == 0.0)


def test_hosttemp_sandbox_without_the_sweeper_module_starts_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        ht, root, records = _ht_fixture(tmp, sweeper=False)
        popen = _Popen()
        got = ht.assess(root, {}, now=NOW, popen=popen)
        _check(got["due"] and not got["spawned"] and popen.calls == [])
        _check(not (records / ht.LOCK_NAME).exists())


def test_hosttemp_rows_printed_once_per_session():
    with tempfile.TemporaryDirectory() as tmp:
        ht, root, records = _ht_fixture(tmp, leases=0)
        _last(ht, records, NOW - 60)
        _rows(
            records,
            "removed tree agent-a (2.1 GB)",
            "killed 4 processes in agent-a (node x4)",
            ts=NOW - 30,
        )
        state: dict = {}
        first = ht.assess(root, state, now=NOW)
        want = "host-temp: removed tree agent-a (2.1 GB); killed 4 processes in agent-a (node x4)"
        _check(first["print"] == [want])
        _check(ht.assess(root, state, now=NOW + 5)["print"] == [])
        _rows(records, "swept 3 dead run dirs (/tmp)", ts=NOW + 10)
        again = ht.assess(root, state, now=NOW + 20)
        _check(again["print"] == ["host-temp: swept 3 dead run dirs (/tmp)"])
        _check(ht.assess(root, state, now=NOW + 30)["print"] == [])


def test_hosttemp_a_peer_session_prints_the_rows_once_as_well():
    with tempfile.TemporaryDirectory() as tmp:
        ht, root, records = _ht_fixture(tmp, leases=0)
        _last(ht, records, NOW - 60)
        mine: dict = {}
        peer: dict = {}
        ht.assess(root, mine, now=NOW - 100)
        ht.assess(root, peer, now=NOW - 100)
        _rows(records, "removed temp of agent-b (0.4 GB)", ts=NOW - 30)
        want = ["host-temp: removed temp of agent-b (0.4 GB)"]
        _check(ht.assess(root, mine, now=NOW)["print"] == want)
        _check(ht.assess(root, peer, now=NOW)["print"] == want)
        _check(ht.assess(root, mine, now=NOW + 1)["print"] == [])
        _check(ht.assess(root, peer, now=NOW + 1)["print"] == [])


def test_hosttemp_a_new_session_skips_rows_older_than_its_window():
    with tempfile.TemporaryDirectory() as tmp:
        ht, root, records = _ht_fixture(tmp, leases=0)
        _last(ht, records, NOW - 60)
        _rows(records, "removed tree agent-old (1.0 GB)", ts=NOW - ht.NEW_SESSION_WINDOW_S - 60)
        _rows(records, "removed tree agent-new (1.0 GB)", ts=NOW - 60)
        got = ht.assess(root, {}, now=NOW)
        _check(got["print"] == ["host-temp: removed tree agent-new (1.0 GB)"])


def _load_ci_paths(path):
    """The canonical `.ci` hop, `rediacc_ci/paths.py`, loaded by file because nothing under `.ci` is importable yet (as test-wl_worktrees.py does). A missing file is said by name: `spec_from_file_location` returns a spec for any `.py` path, so only an existence check reaches that message (review b7e87871.1)."""
    if not path.is_file():
        raise AssertionError("%s is missing" % path)
    spec = importlib.util.spec_from_file_location("_ci_paths", path)
    if spec is None or spec.loader is None:
        raise AssertionError("%s cannot be loaded" % path)
    paths = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paths)
    return paths


def test_hosttemp_control_a_missing_paths_module_is_named():
    with tempfile.TemporaryDirectory() as tmp:
        absent = pathlib.Path(tmp) / "rediacc_ci" / "paths.py"
        try:
            _load_ci_paths(absent)
        except AssertionError as exc:
            _check(str(absent) in str(exc) and "missing" in str(exc))
        else:
            raise AssertionError("a missing paths.py loaded")


def test_hosttemp_lock_agrees_with_the_sweeper_module():
    """The hook and rediacc_ci.dev.host_temp share one lock file and one record shape."""
    paths = _load_ci_paths(REPO / ".ci" / "rediacc_ci" / "paths.py")
    paths.on_sys_path(REPO / ".ci")
    host_temp = importlib.import_module("rediacc_ci.dev.host_temp")
    with tempfile.TemporaryDirectory() as tmp:
        ht, root, records = _ht_fixture(tmp)
        popen = _Popen()
        _check(ht.assess(root, {}, now=time.time(), popen=popen)["spawned"])
        token = popen.calls[0][1]["env"][ht.LOCK_HANDOFF_ENV]
        _check(not host_temp.take_lock(root / ".git", "other"))
        _check(not host_temp.release_lock(root / ".git", "other"))
        _check(host_temp.release_lock(root / ".git", token))
        _check(not (records / ht.LOCK_NAME).exists())
        _check(host_temp.take_lock(root / ".git", "manual"))
        _check(ht.lock_held(records, time.time()))


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as exc:  # report every failing case, then exit 1
                failed += 1
                print("FAIL %s: %r" % (name, exc))
            else:
                print("ok   %s" % name)
    with contextlib.suppress(BrokenPipeError):
        sys.stdout.flush()
    sys.exit(1 if failed else 0)
