"""One event-log fold and one transcript tail per Stop run (agent/plans/PLAN-tooling-speed.md SP1, design D1).

The Stop hook re-read the event log about ten times and the transcript tail about twelve times per stop. A per-process memo keyed on (path, mtime, size) now serves both, and `S.save_state` holds its writes and flushes them once.

HOW THE OPENS ARE COUNTED. The hook runs in a real subprocess under a small launcher that installs a `sys.addaudithook` probe before `runpy` starts worklist.py. CPython raises the `open` audit event for builtins.open, io.open, pathlib's readers and os.open alike, so the probe sees every read-mode open of a watched path whichever API made it, and `os.rename` for the os.replace that lands a state write. Each hit is appended to a side file at once, naming the hook frames that made it, so a failure names the reader.

EVERY POSITIVE HAS ITS CONTROL: with the memo off the same probe counts several reads (it is not blind), and the memo re-reads a file whose size or mtime moved between two loads (it cannot serve a stale world, the one risk the plan names for D1).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest
import wl_common
import wl_core as C
import wl_store as S

from rediacc_hooks.tests import wlfix

PROBE = textwrap.dedent(
    """
    import json, os, runpy, sys
    hook, out = sys.argv[1], sys.argv[2]
    watch = json.loads(sys.argv[3])
    def note(name):
        f, where = sys._getframe(2), []
        while f is not None and len(where) < 3:
            base = os.path.basename(f.f_code.co_filename)
            if base.startswith(("wl_", "worklist")):
                where.append("%s:%d:%s" % (base, f.f_lineno, f.f_code.co_name))
            f = f.f_back
        fd = os.open(out, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        os.write(fd, ("%s %s\\n" % (name, "<".join(where) or "?")).encode())
        os.close(fd)
    def audit(ev, args):
        if ev == "os.rename":
            if os.path.abspath(os.fsdecode(args[1])) == watch["state"]:
                note("state")
            return
        if ev != "open":
            return
        path, mode, flags = args
        if not isinstance(path, (str, bytes, os.PathLike)):
            return
        if isinstance(mode, str) and any(c in mode for c in "wax+"):
            return
        if isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR):
            return
        p = os.path.abspath(os.fsdecode(path))
        if p == watch["transcript"]:
            note("transcript")
        elif p in watch["events"]:
            note("events")
    sys.addaudithook(audit)
    sys.argv = [hook]
    sys.path.insert(0, os.path.dirname(hook))
    runpy.run_path(hook, run_name="__main__")
    """
)

# READERS THAT OPEN THE TRANSCRIPT THEMSELVES, outside SP1's file set, each with the reason it is not served yet. Every entry must still open the transcript on the fixture stop (test_every_named_reader_still_opens), so a reader moved onto `wl_core.tail_bytes` fails the suite until its entry is deleted: this list can only shrink.
UNSERVED_TRANSCRIPT_READERS = {
    "wl_admit.py:turn_tools": "BLOCKER: wl_admit.py is outside PLAN-tooling-speed.md's Owns; turn_tools opens the transcript itself instead of calling wl_core.tail_bytes",
    "wl_uncommitted.py:scan_transcript": "BLOCKER: wl_uncommitted.py is SP2's file; scan_transcript moves onto wl_core.tail_bytes there",
}


def counted_stop(fix: wlfix.Fixture, tmp, extra: dict | None = None) -> tuple[dict, wlfix.Result]:
    """One fixture Stop run under the probe: {"events"|"transcript"|"state": count, "where": [...]}, and the hook's result with `battery_ran` set."""
    probe = tmp / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    out = tmp / "opens.txt"
    if out.exists():
        out.unlink()
    watch = {
        "events": [str(f.resolve()) for f in sorted(fix.store_dir.glob("*.jsonl"))],
        "transcript": str(fix.transcript.resolve()),
        "state": str(fix.stem(".state-%s.json" % wlfix.ME).resolve()),
    }
    before = fix._lastevents()
    proc = subprocess.run(
        [sys.executable, str(probe), str(fix.hook), str(out), json.dumps(watch)],
        input=fix.event(),
        capture_output=True,
        text=True,
        env=fix.stop_env(extra),
        check=False,
    )
    counts: dict = {"events": 0, "transcript": 0, "state": 0, "where": []}
    if out.is_file():
        for line in out.read_text(encoding="utf-8").splitlines():
            name, _, where = line.partition(" ")
            counts[name] += 1
            counts["where"].append("%s from %s" % (name, where))
    got = wlfix.Result(proc.stdout, proc.stderr, proc.returncode)
    got.battery_ran = proc.returncode == 0 and fix._lastevents() != before
    return counts, got


def _site_of(where: str) -> str:
    first = where.split(" from ", 1)[1].split("<", 1)[0]
    parts = first.split(":")
    return "%s:%s" % (parts[0], parts[-1])


def unserved(counts: dict) -> list[str]:
    """The transcript opens made by a named unserved reader."""
    return [
        w
        for w in counts["where"]
        if w.startswith("transcript from ") and _site_of(w) in UNSERVED_TRANSCRIPT_READERS
    ]


def world(fix: wlfix.Fixture) -> None:
    """A store with a CLI-written item (so the event log has a writer file) and a transcript with a finished message."""
    got = fix.cli("--add", wlfix.ME, "probe the read memo")
    assert got.rc == 0, got.err[-800:]
    fix.say("done\n\n## Remaining\n- the probe item")
    fix.brief_now()
    fix.hand_now()


def test_one_stop_reads_the_event_log_once_and_the_transcript_once(wl, tmp_path):
    world(wl)
    files = sorted(wl.store_dir.glob("*.jsonl"))
    assert files, "the fixture wrote no store file, so a count of 1 would prove nothing"
    counts, got = counted_stop(wl, tmp_path)
    assert got.battery_ran, (
        "the Stop battery did not run, so the counts measure nothing: %s" % got.err[-800:]
    )
    # ZERO would mean the probe is blind, not that the hook is fast.
    assert counts["events"] == len(files), counts
    assert counts["transcript"] - len(unserved(counts)) == 1, counts
    assert counts["state"] <= 1, counts


def test_the_probe_is_not_blind_with_the_memo_off(wl, tmp_path):
    """CONTROL: WORKLIST_READ_MEMO=off restores the old reads, and the same probe then counts several reads of the event log and of the transcript, and more than one state write."""
    world(wl)
    files = sorted(wl.store_dir.glob("*.jsonl"))
    counts, got = counted_stop(wl, tmp_path, {"WORKLIST_READ_MEMO": "off"})
    assert got.battery_ran, got.err[-800:]
    assert counts["events"] > len(files), counts
    assert counts["transcript"] - len(unserved(counts)) > 1, counts
    assert counts["state"] > 1, counts


def test_every_named_reader_still_opens(wl, tmp_path):
    """The exemption list is live: each named reader still opens the transcript itself on the fixture stop. One that no longer does is served, and its entry must go."""
    world(wl)
    counts, got = counted_stop(wl, tmp_path)
    assert got.battery_ran, got.err[-800:]
    seen = {_site_of(w) for w in unserved(counts)}
    stale = sorted(set(UNSERVED_TRANSCRIPT_READERS) - seen)
    assert not stale, "no longer opens the transcript itself; delete its entry: %s" % stale


@pytest.fixture
def memo(wl, monkeypatch):
    """The fixture store's environment with both memos cleared."""
    for key, value in wl.stop_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("WORKLIST_READ_MEMO", raising=False)
    S.clear_read_memo()
    C.clear_read_memo()
    yield wl
    S.clear_read_memo()
    C.clear_read_memo()


def test_a_write_between_two_loads_is_seen(memo):
    """CONTROL for the memo: the second load is served when the event log did not move, and the third re-reads after a write."""
    world(memo)
    first = S.load(memo.wl, sync=False)
    ids = {r["id"] for r in first.items}
    again = S.load(memo.wl, sync=False)
    assert {r["id"] for r in again.items} == ids
    assert S.READ_MEMO_STATS == {"hit": 1, "miss": 1}
    got = memo.cli("--add", wlfix.ME, "a second item written between the loads")
    assert got.rc == 0, got.err[-600:]
    third = S.load(memo.wl, sync=False)
    assert len({r["id"] for r in third.items} - ids) == 1, [r["text"] for r in third.items]
    assert S.READ_MEMO_STATS["miss"] == 2


def test_a_served_fold_is_a_copy(memo):
    """A caller mutating its fold cannot change what the next caller is served."""
    world(memo)
    first = S.load(memo.wl, sync=False)
    first.items[0]["text"] = "MUTATED"
    first.items.append({"id": "zz"})
    again = S.load(memo.wl, sync=False)
    assert "MUTATED" not in [r["text"] for r in again.items]
    assert "zz" not in again.by_id


def test_the_transcript_tail_is_re_read_when_the_transcript_grows(memo):
    world(memo)
    text, _tools, ok = C.transcript_tail(str(memo.transcript))
    assert ok
    assert "## Remaining" in text
    assert C.READ_MEMO_STATS["miss"] == 1
    C.transcript_tail(str(memo.transcript))
    assert C.READ_MEMO_STATS["miss"] == 1
    assert C.READ_MEMO_STATS["hit"] >= 1
    memo.newturn()
    memo.say("a later message")
    text, _tools, ok = C.transcript_tail(str(memo.transcript))
    assert text == "a later message"
    assert C.READ_MEMO_STATS["miss"] == 2


def test_a_smaller_tail_is_sliced_from_a_larger_read(memo):
    """A reader asking for fewer bytes is served from the bytes already read, with the partial first line dropped exactly as wl_common.tail_records drops it."""
    big = memo.transcript
    big.write_text(
        "".join(json.dumps({"type": "user", "n": i}) + "\n" for i in range(400)), encoding="utf-8"
    )
    whole = C.tail_records(str(big), 10**6)
    assert len(whole) == 400
    small = C.tail_records(str(big), 2000)
    assert C.READ_MEMO_STATS["miss"] == 1
    raw = big.read_bytes()
    assert small == [json.loads(ln) for ln in raw[-2000:].split(b"\n")[1:] if ln.strip()]


def test_wl_common_readers_are_served_from_the_memo(memo):
    """wl_admit.turn_text and wl_deflect call wl_common.tail_records; after wl_core is imported that name is the memoized reader."""

    assert memo.transcript.is_file()
    assert wl_common.tail_records is C.tail_records


def test_state_writes_flush_once_per_batch(memo):
    """`S.save_state` inside a batch writes nothing until the batch closes, then the last doc once; a read inside the batch sees the pending doc; outside a batch it writes at once."""
    path = S.state_path(memo.wl, wlfix.ME)
    with S.state_batch():
        for n in range(5):
            S.save_state(memo.wl, wlfix.ME, {"n": n})
            assert S.load_state(memo.wl, wlfix.ME) == {"n": n}
        assert not path.exists(), "a batched save reached the disk before the flush"
    assert json.loads(path.read_text(encoding="utf-8")) == {"n": 4}
    assert S.STATE_FLUSHES["n"] == 1
    S.save_state(memo.wl, wlfix.ME, {"n": 9})
    assert json.loads(path.read_text(encoding="utf-8")) == {"n": 9}


def crash_in_batch(worklist):
    with S.state_batch():
        S.save_state(worklist, wlfix.ME, {"crash": True})
        raise RuntimeError("boom")


def test_state_writes_flush_on_an_exception(memo):
    path = S.state_path(memo.wl, wlfix.ME)
    with pytest.raises(RuntimeError):
        crash_in_batch(memo.wl)
    assert json.loads(path.read_text(encoding="utf-8")) == {"crash": True}


def test_a_stop_that_crashes_still_writes_its_state(wl, tmp_path):
    """CONTROL for the Stop-process batch: a battery that raises after a save still lands the doc, through atexit."""
    world(wl)
    probe = tmp_path / "crash.py"
    probe.write_text(
        textwrap.dedent(
            """
            import pathlib, sys
            sys.path.insert(0, sys.argv[1])
            _RUN = {"stop": True}
            import wl_store as S
            S.save_state(pathlib.Path(sys.argv[2]), "deadbeef", {"saved": "before the crash"})
            print("pending=%d" % len(S._PENDING_STATE))
            raise RuntimeError("battery crashed")
            """
        ),
        encoding="utf-8",
    )
    path = wl.stem(".state-%s.json" % wlfix.ME)
    proc = subprocess.run(
        [sys.executable, str(probe), str(wlfix.STOP_DIR), str(wl.wl)],
        capture_output=True,
        text=True,
        env=wl.stop_env(),
        check=False,
    )
    assert proc.returncode == 1, proc.stderr[-600:]
    assert "battery crashed" in proc.stderr
    assert "pending=1" in proc.stdout, (
        "the Stop process wrote at once, so this proves nothing about the batch"
    )
    assert json.loads(path.read_text(encoding="utf-8")) == {"saved": "before the crash"}
