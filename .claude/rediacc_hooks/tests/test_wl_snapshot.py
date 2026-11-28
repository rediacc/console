"""wl_snapshot (agent/plans/PLAN-tooling-code-reduction.md CR9): finished sessions' logs folded into one snapshot.

Each test builds a disposable store (WORKLIST_STORE_DIR) with a finished writer, a recent writer and the epics sidecar, then compares the fold before and after. EVERY POSITIVE HAS ITS CONTROL: a recent writer's log and the epics sidecar survive, and a store with nothing finished is left byte for byte.
"""

from __future__ import annotations

import json
import os
import pathlib
import types

import pytest
import wl_core as C
import wl_snapshot as W
import wl_store as S

OLD = "2026-10-01T00:00:00Z"


def ev(kind, by, at, **kw):
    return json.dumps({"ev": kind, "by": by, "at": at, **kw}, separators=(",", ":")) + "\n"


@pytest.fixture
def store(tmp_path, monkeypatch):
    d = tmp_path / "store"
    d.mkdir()
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("WORKLIST_STORE_DIR", str(d))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("WORKLIST_READ_MEMO", "off")
    recent = C.stamp_now()
    # dead0001 finished long ago: it added two items, ticked one, and ticked an item the recent writer added.
    (d / "dead0001.jsonl").write_text(
        ev("add", "dead0001", OLD, id="a1", s=" ", o="dead0001", t="open item of the dead session")
        + ev(
            "add", "dead0001", OLD, id="a2", s=" ", o="dead0001", t="done item of the dead session"
        )
        + ev("state", "dead0001", "2026-10-01T00:05:00Z", id="a2", s="x", note="done")
        + ev(
            "state", "dead0001", "2026-10-01T00:06:00Z", id="b1", s="x", note="ticked a peer's item"
        ),
        encoding="utf-8",
    )
    (d / "beef0002.jsonl").write_text(
        ev(
            "add",
            "beef0002",
            "2026-09-30T00:00:00Z",
            id="b1",
            s=" ",
            o="beef0002",
            t="item of the recent writer",
        )
        + ev("add", "beef0002", recent, id="b2", s=" ", o="beef0002", t="a later open item"),
        encoding="utf-8",
    )
    (d / "epics.jsonl").write_text(
        json.dumps({"at": OLD, "by": "dead0001", "id": "e1", "title": "an epic"}) + "\n",
        encoding="utf-8",
    )
    return types.SimpleNamespace(d=d, root=proj, wl=tmp_path / "WORKLIST.md", tmp=tmp_path)


def states(s):
    fold = S.load(s.wl, sync=False)
    return {r["id"]: r["state"] for r in fold.items}


def run(s, flag):
    return W.main(
        [flag], worklist=s.wl, root=s.root, me="cafe0003", projects_dir=s.tmp / "no-transcripts"
    )


def test_plan_names_the_finished_log_and_not_the_recent_or_the_sidecar(store, capsys):
    assert run(store, "--plan") == 0
    out = capsys.readouterr().out
    assert "dead0001.jsonl" in out
    assert "beef0002.jsonl" not in out
    assert "epics.jsonl" not in out
    assert "1 file(s)" in out
    assert (store.d / "dead0001.jsonl").exists(), "--plan wrote"


def test_write_folds_to_the_same_state_and_the_finished_log_is_gone(store):
    before = states(store)
    assert before == {"a1": " ", "a2": "x", "b1": "x", "b2": " "}
    assert run(store, "--write") == 0
    assert not (store.d / "dead0001.jsonl").exists()
    assert (store.d / "cafe0003.jsonl").exists(), "the snapshot is not written"
    assert states(store) == before, "folding finished logs changed the world"


def test_no_per_stop_read_opens_a_finished_log_after_the_fold(store, monkeypatch):
    run(store, "--write")
    opened = []
    real = pathlib.Path.read_text

    def spy(self, *a, **kw):
        opened.append(self.name)
        return real(self, *a, **kw)

    monkeypatch.setattr(pathlib.Path, "read_text", spy)
    S._read_events(store.wl, store.root)
    assert opened, "the spy saw no read, so it measures nothing"
    assert "dead0001.jsonl" not in opened


def test_the_epics_sidecar_survives_a_fold(store):
    run(store, "--write")
    assert (store.d / "epics.jsonl").exists(), "compact_store unlinked the epics sidecar"


def test_a_recent_writers_log_is_kept(store):
    run(store, "--write")
    assert (store.d / "beef0002.jsonl").exists()


def test_the_plan_and_the_write_agree_on_which_files_go(store):
    found = W.finished_logs(store.wl, store.root, "cafe0003", store.tmp / "x")
    planned = {p.name for p, _n, _v in found}
    before = {p.name for p in store.d.glob("*.jsonl")}
    run(store, "--write")
    gone = before - {p.name for p in store.d.glob("*.jsonl")}
    assert planned == {"dead0001.jsonl"}
    assert gone == planned


def test_nothing_finished_changes_nothing(store, capsys):
    (store.d / "dead0001.jsonl").unlink()
    snap = {p.name: p.read_bytes() for p in store.d.glob("*.jsonl")}
    assert run(store, "--write") == 0
    assert "nothing to fold" in capsys.readouterr().out
    assert {p.name: p.read_bytes() for p in store.d.glob("*.jsonl")} == snap


def test_an_unknown_flag_is_usage(store, capsys):
    assert W.main(["--bogus"], worklist=store.wl, root=store.root) == 2
    assert "wl_snapshot" in capsys.readouterr().err


def hk(s, stamp, now, rotate=None):
    return W.housekeeping(
        s.wl,
        stamp,
        root=s.root,
        me="cafe0003",
        projects_dir=s.tmp / "no-transcripts",
        now=now,
        rotate=rotate or (lambda: None),
    )


def test_housekeeping_runs_when_the_stamp_is_missing_or_stale_and_skips_when_fresh(store):
    stamp = store.tmp / "stamp"
    calls = []
    assert hk(store, stamp, 1000.0, lambda: calls.append("rotate")) == {}
    assert calls == ["rotate"]
    assert not (store.d / "dead0001.jsonl").exists(), "the fold did not run"
    assert stamp.stat().st_mtime == 1000.0
    # Control: inside 24 h nothing runs, the stamp is not moved.
    assert hk(store, stamp, 1000.0 + 3600, lambda: calls.append("again")) == {}
    assert calls == ["rotate"]
    assert stamp.stat().st_mtime == 1000.0
    # Past 24 h it runs again.
    hk(store, stamp, 1000.0 + 25 * 3600, lambda: calls.append("later"))
    assert calls == ["rotate", "later"]


def test_housekeeping_names_a_failed_step_and_does_not_raise_or_skip_the_other(store):
    def boom():
        raise RuntimeError("ledger unreadable")

    failures = hk(store, store.tmp / "stamp", 1000.0, boom)
    assert set(failures) == {"hook-ledger-rotate"}
    assert "ledger unreadable" in str(failures["hook-ledger-rotate"])
    assert not (store.d / "dead0001.jsonl").exists(), "a rotate failure skipped the fold"
    # Control: a clean run names nothing, and a failed one is not retried inside the window.
    assert hk(store, store.tmp / "stamp2", 1000.0) == {}
    assert hk(store, store.tmp / "stamp", 1001.0, boom) == {}


def test_a_stamp_dated_in_the_future_is_stale_not_fresh(store):
    stamp = store.tmp / "stamp"
    calls = []
    hk(store, stamp, 1000.0)
    os.utime(stamp, (5000.0, 5000.0))  # clock once set ahead
    assert hk(store, stamp, 1000.0 + 3600, lambda: calls.append("ran")) == {}
    assert calls == ["ran"]
    assert stamp.stat().st_mtime == 1000.0 + 3600
    # control: a stamp one hour old stays fresh
    assert hk(store, stamp, 1000.0 + 2 * 3600, lambda: calls.append("again")) == {}
    assert calls == ["ran"]


def test_an_unwritable_stamp_is_named_and_the_steps_do_not_run_every_stop(store):
    calls = []
    stamp = store.tmp / "no-such-dir" / "stamp"
    failures = hk(store, stamp, 1000.0, lambda: calls.append("rotate"))
    assert set(failures) == {"snapshot-stamp"}
    assert calls == []
    # control: a writable stamp runs the steps
    assert hk(store, store.tmp / "stamp", 1000.0, lambda: calls.append("rotate")) == {}
    assert calls == ["rotate"]


def test_housekeeping_fold_writes_nothing_to_stdout(store, capsys):
    hk(store, store.tmp / "stamp", 1000.0)
    cap = capsys.readouterr()
    assert cap.out == "", "a Stop's stdout is the hook's JSON answer"
    assert "compacted 1 file(s)" in cap.err


def test_housekeeping_rotate_writes_nothing_to_stdout(store, capsys):
    def noisy():
        print("rotated 3 ledgers")

    hk(store, store.tmp / "stamp", 1000.0, noisy)
    cap = capsys.readouterr()
    assert cap.out == "", "a print inside the rotate step reached the hook's stdout JSON"
    assert "rotated 3 ledgers" in cap.err


def test_an_unwritable_stamp_is_named_on_every_stop(store):
    stamp = store.tmp / "no-such-dir" / "stamp"
    assert set(hk(store, stamp, 1000.0)) == {"snapshot-stamp"}
    assert set(hk(store, stamp, 1001.0)) == {"snapshot-stamp"}


@pytest.mark.parametrize("value", ["soon", "", "0", "-5"])
def test_a_bad_dead_hours_value_falls_back_to_a_day(store, monkeypatch, value):
    monkeypatch.setenv("WORKLIST_DEAD_HOURS", value)
    assert S.dead_hours() == 24.0
    found = W.finished_logs(store.wl, store.root, "cafe0003", store.tmp / "no-transcripts")
    assert {pathlib.Path(p).name for p, _n, _v in found} == {"dead0001.jsonl"}


def test_a_good_dead_hours_value_is_read(monkeypatch):
    monkeypatch.setenv("WORKLIST_DEAD_HOURS", "6.5")
    assert S.dead_hours() == 6.5


def test_an_unreadable_stamp_dir_is_named_not_raised(store, monkeypatch):
    """0bddf781.1: a PermissionError from the stamp's stat (an unsearchable stamp directory) is named as snapshot-stamp, never escapes housekeeping. Control: a readable stamp runs clean."""
    stamp = store.tmp / "stamp"
    real_stat = pathlib.Path.stat

    def stat(self, *a, **k):
        if self == stamp:
            raise PermissionError("planted")
        return real_stat(self, *a, **k)

    with monkeypatch.context() as m:
        m.setattr(pathlib.Path, "stat", stat)
        assert set(hk(store, stamp, 1000.0)) == {"snapshot-stamp"}
    assert hk(store, stamp, 1000.0) == {}
