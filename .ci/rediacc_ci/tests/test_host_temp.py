"""host_temp: finished-lease sweep, dead run dirs and `reclaim --legacy` (agent/plans/PLAN-host-temp-disposal.md HT12).

Every case works inside its own tmp_path: the fixture repo, tree, tmpdir and bases are all fixtures, and processes are real `sleep` children of the test with their cwd in a fixture directory. gc is a stand-in that removes or keeps the fixture tree, so no real checkout is touched.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import time

import pytest

from rediacc_ci import runtmp
from rediacc_ci.dev import host_temp as ht

NOW = 1_000_000.0
LEASE = "agent-a0123456789abcdef"


class Fix:
    def __init__(self, tmp_path: pathlib.Path):
        self.tmp = tmp_path
        self.root = tmp_path / "repo"
        self.common = self.root / ".git"
        self.records = self.common / ht.RECORD_DIR
        self.records.mkdir(parents=True)
        self.tree = self.root / ".claude" / "worktrees" / LEASE
        self.tree.mkdir(parents=True)
        (self.tree / "work.txt").write_text("x")
        self.tmpdir = tmp_path / "vt" / "abcd1234"
        self.tmpdir.mkdir(parents=True)
        (self.tmpdir / "scratch").write_text("y" * 4096)
        self.home = tmp_path / "home"
        self.cache = self.home / ".cache" / "rediacc-typecheck"
        self.cache.mkdir(parents=True)
        self.procs: list[subprocess.Popen] = []
        self.transcript = tmp_path / "agent.jsonl"
        self.transcript.write_text("{}\n")
        (tmp_path / "agent.meta.json").write_text(json.dumps({"finished": True}))
        os.utime(self.transcript, (NOW - 7200, NOW - 7200))
        (self.records / (LEASE + ".json")).write_text(
            json.dumps({"id": LEASE, "path": str(self.tree), "tmpdir": str(self.tmpdir)})
        )
        self.mark(NOW - 31 * 60)

    def mark(self, finished_at: float) -> None:
        body = {"agent": "a0123456789abcdef", "finished_at": finished_at}
        body["transcript"] = str(self.transcript)
        (self.records / (LEASE + ht.MARKER_SUFFIX)).write_text(json.dumps(body))

    def sleeper(self, cwd: pathlib.Path) -> subprocess.Popen:
        proc = subprocess.Popen(["sleep", "300"], cwd=str(cwd))
        self.procs.append(proc)
        deadline = time.time() + 5
        while ht.start_time(proc.pid) < 0 and time.time() < deadline:
            time.sleep(0.01)
        return proc

    def gc(self, keep: str = ""):
        def run(_root, lease_id):
            if keep:
                return 0, ["  KEEP    %-24s %s; more" % (lease_id, keep)]
            for child in sorted(self.tree.rglob("*"), reverse=True):
                child.unlink() if child.is_file() else child.rmdir()
            self.tree.rmdir()
            return 0, []

        return run

    def sweep(self, *, busy=lambda _id: "", gc=None, scan=ht.scan_procs, now=NOW, token=""):
        return ht.sweep(
            self.root,
            now=now,
            busy=busy,
            gc=gc or self.gc(),
            scan=scan,
            bases=[],
            home=str(self.home),
            token=token,
            term_wait=2.0,
        )

    def sweep_locked(self):
        """A manual sweep (no `--lock-held`): it must take the lock itself."""
        return ht.sweep(
            self.root,
            now=NOW,
            busy=lambda _id: "",
            gc=self.gc(),
            bases=[],
            home=str(self.home),
            lock_held=False,
            term_wait=2.0,
        )

    def close(self) -> None:
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()
            proc.wait()


@pytest.fixture
def fx(tmp_path):
    fixture = Fix(tmp_path)
    yield fixture
    fixture.close()


def _alive(proc: subprocess.Popen) -> bool:
    return proc.poll() is None


def test_finished_31_minutes_kills_deletes_and_removes_the_tree(fx):
    in_tree, in_tmp = fx.sleeper(fx.tree), fx.sleeper(fx.tmpdir)
    rows = fx.sweep()
    assert in_tree.wait(timeout=5) != 0
    assert in_tmp.wait(timeout=5) != 0
    assert not fx.tmpdir.exists()
    assert not fx.tree.exists()
    assert any(r.startswith("removed tree %s" % LEASE) for r in rows), rows
    assert any("killed 2 processes in %s (sleep x2)" % LEASE in r for r in rows), rows
    assert not (fx.records / (LEASE + ht.MARKER_SUFFIX)).exists()
    logged = (fx.records / ht.SWEEPS).read_text().splitlines()
    assert [json.loads(line)["text"] for line in logged] == rows


def test_finished_29_minutes_does_nothing(fx):
    fx.mark(NOW - 29 * 60)
    proc = fx.sleeper(fx.tree)
    assert fx.sweep() == []
    assert _alive(proc)
    assert fx.tmpdir.exists()
    assert fx.tree.exists()


def test_control_without_the_1800_second_check_the_29_minute_lease_is_swept(fx, monkeypatch):
    """The planted defect: the grace check removed. The same fixture as the 29-minute case now loses its tmpdir, so that case's assertions are the ones that catch it."""
    fx.mark(NOW - 29 * 60)
    real = ht.finished_problem

    def no_grace(common, lease_id, now, **kw):
        return real(common, lease_id, now, **{**kw, "grace": 0})

    monkeypatch.setattr(ht, "finished_problem", no_grace)
    fx.sweep()
    assert not fx.tmpdir.exists()


def test_resumed_agent_meta_not_finished_does_nothing(fx):
    (fx.tmp / "agent.meta.json").write_text(json.dumps({}))
    proc = fx.sleeper(fx.tree)
    assert fx.sweep() == []
    assert _alive(proc)
    assert fx.tmpdir.exists()
    assert fx.tree.exists()


def test_open_worklist_item_naming_the_lease_does_nothing(fx):
    proc = fx.sleeper(fx.tree)
    assert fx.sweep(busy=lambda _id: "worklist item #abc names it") == []
    assert _alive(proc)
    assert fx.tmpdir.exists()
    assert fx.tree.exists()


def test_recent_transcript_write_does_nothing(fx):
    os.utime(fx.transcript, (NOW - 60, NOW - 60))
    assert fx.sweep() == []
    assert fx.tmpdir.exists()


def test_unreadable_transcript_counts_as_busy(fx):
    """Review f2b58581.1: a transcript whose stat fails proves nothing about the agent's quiet time, so the lease is not swept."""
    body = json.loads((fx.records / (LEASE + ht.MARKER_SUFFIX)).read_text())
    body["transcript"] = str(fx.transcript / "not-a-dir")
    (fx.records / (LEASE + ht.MARKER_SUFFIX)).write_text(json.dumps(body))
    proc = fx.sleeper(fx.tree)
    assert ht.finished_problem(fx.common, LEASE, NOW).startswith("transcript unreadable")
    assert fx.sweep() == []
    assert _alive(proc)
    assert fx.tmpdir.exists()
    assert fx.tree.exists()


def test_lock_is_exclusive_while_its_holder_lives(fx):
    assert ht.take_lock(fx.common, "t1")
    assert not ht.take_lock(fx.common, "t2")
    assert fx.sweep_locked() == []
    assert fx.tmpdir.exists()


def test_lock_of_a_dead_holder_is_taken_over(fx):
    dead = subprocess.Popen(["true"])
    dead.wait()
    lock = fx.records / ht.LOCK_NAME
    lock.write_text(json.dumps({"pid": dead.pid, "start": 1, "token": "old"}))
    assert ht.take_lock(fx.common, "new")
    assert json.loads(lock.read_text())["token"] == "new"


def test_lock_released_only_with_its_own_token(fx):
    assert ht.take_lock(fx.common, "mine")
    assert not ht.release_lock(fx.common, "other")
    assert (fx.records / ht.LOCK_NAME).exists()
    assert ht.release_lock(fx.common, "mine")
    assert not (fx.records / ht.LOCK_NAME).exists()


def test_a_handed_over_sweep_releases_the_lock_it_was_given(fx):
    assert ht.take_lock(fx.common, "handoff")
    fx.sweep(token="handoff")
    assert not (fx.records / ht.LOCK_NAME).exists()


def test_control_a_sweep_without_the_token_leaves_the_lock(fx):
    assert ht.take_lock(fx.common, "handoff")
    fx.sweep()
    assert (fx.records / ht.LOCK_NAME).exists()


def test_unlanded_commit_keeps_the_tree_and_removes_the_temp(fx):
    rows = fx.sweep(gc=fx.gc(keep="rule 4: 1 unlanded commit"))
    assert fx.tree.exists()
    assert not fx.tmpdir.exists()
    assert any(r.startswith("kept tree %s (rule 4: 1 unlanded commit)" % LEASE) for r in rows), rows
    assert (fx.records / (LEASE + ht.MARKER_SUFFIX)).exists()


def test_pid_reused_between_scan_and_kill_is_not_killed(fx):
    bystander = fx.sleeper(fx.tree)
    real = ht.scan_procs()
    stale = [p._replace(start=p.start + 1) if p.pid == bystander.pid else p for p in real]
    assert any(p.pid == bystander.pid for p in stale)
    killed = ht.kill_in([str(fx.tree)], scan=lambda: stale, term_wait=0.2)
    assert killed == []
    assert _alive(bystander)


def test_dead_pid_run_dirs_removed_in_each_base_and_live_ones_kept(tmp_path):
    bases = [tmp_path / "b1", tmp_path / "b2"]
    gone = subprocess.Popen(["true"])
    gone.wait()
    live = subprocess.Popen(["sleep", "300"])
    try:
        dead_dirs: list[pathlib.Path] = []
        live_dirs: list[pathlib.Path] = []
        for base in bases:
            base.mkdir()
            for prefix, bucket, pid in (
                ("path-trace-", dead_dirs, gone.pid),
                ("rediacc-pytest-", live_dirs, live.pid),
            ):
                path = base / (runtmp.stamp(prefix, pid) + "abc")
                path.mkdir()
                (path / "f").write_text("x")
                bucket.append(path)
        removed = ht.sweep_dead_runs([str(b) for b in bases])
        assert sorted(removed) == sorted(str(p) for p in dead_dirs)
        assert not any(p.exists() for p in dead_dirs)
        assert all(p.exists() for p in live_dirs)
    finally:
        live.kill()
        live.wait()


def test_reclaim_legacy_keeps_an_open_fd_and_removes_one_without(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    held, free, young = (
        base / n for n in ("path-trace-AAAA", "path-trace-BBBB", "path-trace-CCCC")
    )
    for entry in (held, free, young):
        entry.mkdir()
        (entry / "t.1").write_text("x")
    for entry in (held, free):
        os.utime(entry / "t.1", (NOW - 7200, NOW - 7200))
        os.utime(entry, (NOW - 7200, NOW - 7200))
    os.utime(young / "t.1", (NOW - 10, NOW - 10))
    os.utime(young, (NOW - 10, NOW - 10))
    with open(held / "t.1", encoding="utf-8") as fh:
        holder = subprocess.Popen(["sleep", "300"], stdin=fh)
        try:
            listing = ht.reclaim_legacy([str(base)], write=False, now=NOW)
            assert free.exists(), "the listing never deletes"
            assert any(r.startswith("WOULD-REMOVE %s" % free) for r in listing), listing
            rows = ht.reclaim_legacy([str(base)], write=True, now=NOW)
        finally:
            holder.kill()
            holder.wait()
    assert held.exists()
    assert young.exists()
    assert not free.exists()
    assert any(r.startswith("KEEP %s a process has it open" % held) for r in rows), rows
    assert any(r.startswith("KEEP %s modified" % young) for r in rows), rows


def test_reclaim_legacy_keeps_a_path_trace_dir_a_running_strace_writes_to(tmp_path):
    base = tmp_path / "base"
    entry = base / "path-trace-DDDD"
    entry.mkdir(parents=True)
    os.utime(entry, (NOW - 7200, NOW - 7200))
    rows = ht.reclaim_legacy(
        [str(base)], write=True, now=NOW, open_scan=lambda: (set(), [str(entry / "t")])
    )
    assert entry.exists()
    assert rows == ["KEEP %s a running strace writes to it" % entry]


def test_stamped_dirs_are_left_to_the_dead_run_sweep_not_to_reclaim(tmp_path):
    entry = tmp_path / (runtmp.stamp("path-trace-", 1) + "zz")
    entry.mkdir()
    os.utime(entry, (NOW - 7200, NOW - 7200))
    assert ht.reclaim_legacy([str(tmp_path)], write=True, now=NOW) == []
    assert entry.exists()


def test_status_names_what_the_next_sweep_would_do(fx):
    assert ht.status(fx.root, now=NOW, busy=lambda _id: "") == ["SWEEP %s" % LEASE]
    fx.mark(NOW - 60)
    rows = ht.status(fx.root, now=NOW, busy=lambda _id: "")
    assert rows == ["WAIT %s: finished 60 s ago" % LEASE]


def test_typecheck_caches_of_gone_trees_are_removed_and_others_kept(tmp_path):
    root = tmp_path / "console"
    (root / ".claude" / "worktrees" / "agent-live").mkdir(parents=True)
    cache = tmp_path / "cache"
    head = str(root / ".claude" / "worktrees").lstrip("/").replace("/", "-") + "-"
    for name in (head + "agent-live", head + "agent-gone", "other-checkout-agent-gone"):
        (cache / name).mkdir(parents=True)
    removed = ht.typecheck_orphans(root, str(cache))
    assert [os.path.basename(p) for p in removed] == [head + "agent-gone"]
    assert sorted(os.listdir(cache)) == sorted([head + "agent-live", "other-checkout-agent-gone"])


def test_prefix_registry_covers_every_run_dir_prefix_in_the_tree():
    found = set()
    shape = re.compile(r"""(?:run_dir|shared)\(\s*["']([a-z0-9-]+-)["']""")
    for path in pathlib.Path(runtmp.__file__).parent.rglob("*.py"):
        if path.name == pathlib.Path(__file__).name:
            continue
        found.update(shape.findall(path.read_text(encoding="utf-8", errors="replace")))
    # Prefixes the runtmp unit tests make for themselves, never in a shared base, and the `run_dir('elite-')` source text test_temp_probe.py plants in its fixture repositories.
    found -= {"runtmp-ctl-", "runtmp-other-", "x-", "elite-"}
    assert sorted(found - set(ht.PREFIXES)) == []


def test_a_sweep_refreshes_its_lock_so_a_slow_holder_is_not_taken_over(fx):
    """Review 2872d8fe.3: the lock's age rule must judge a hung holder, not one still sweeping."""
    assert ht.take_lock(fx.common, "slow")
    lock = fx.records / ht.LOCK_NAME
    old = time.time() - 2 * ht.LOCK_STALE_S
    os.utime(lock, (old, old))
    assert ht.lock_is_stale(lock)
    fx.sweep()
    assert time.time() - lock.stat().st_mtime < 60
    assert not ht.lock_is_stale(lock)


def test_a_record_row_that_cannot_be_written_is_said_on_stderr(fx, capsys):
    """Review f2b58581.3: a failed append to sweeps.jsonl is no silent drop."""
    (fx.records / ht.SWEEPS).mkdir()
    ht._record_rows(fx.common, ["row"], NOW)
    assert ht.SWEEPS in capsys.readouterr().err
    # CONTROL: a writable log appends the row and says nothing.
    (fx.records / ht.SWEEPS).rmdir()
    ht._record_rows(fx.common, ["row"], NOW)
    assert capsys.readouterr().err == ""
    assert json.loads((fx.records / ht.SWEEPS).read_text())["text"] == "row"


def test_reclaim_legacy_keeps_a_dir_whose_files_are_rewritten_in_place(tmp_path):
    """Review f2b58581.4: the top-level directory's mtime is old, a file inside it is young."""
    base = tmp_path / "base"
    base.mkdir()
    busy, idle = base / "path-trace-AAAA", base / "path-trace-BBBB"
    for entry in (busy, idle):
        entry.mkdir()
        (entry / "sub").mkdir()
        (entry / "sub" / "t.1").write_text("x")
    for entry in (busy, idle):
        os.utime(entry / "sub" / "t.1", (NOW - 7200, NOW - 7200))
        os.utime(entry / "sub", (NOW - 7200, NOW - 7200))
        os.utime(entry, (NOW - 7200, NOW - 7200))
    os.utime(busy / "sub" / "t.1", (NOW - 10, NOW - 10))
    rows = ht.reclaim_legacy([str(base)], write=True, now=NOW, open_scan=lambda: (set(), []))
    assert busy.exists()
    assert not idle.exists()
    assert any(r.startswith("KEEP %s modified" % busy) for r in rows), rows
