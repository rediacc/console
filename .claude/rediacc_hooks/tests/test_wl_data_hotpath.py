"""Agent data off the hot path (agent/plans/PLAN-tooling-code-reduction.md CR9, design D7).

`agent/ledgers/plan-investigation.jsonl` (about 3 MB) was decoded once per reader in a Stop run: wl_claimcheck, wl_plandeps, wl_planpreflight and wl_planrec each called `wl_planrec.read_investigations`, which re-read and re-parsed the whole file. The rows are now memoized per process on the file's (path, inode, mtime_ns, size).

HOW THE READS ARE COUNTED. The hook runs in a real subprocess under a launcher that installs a `sys.addaudithook` probe before `runpy` starts worklist.py. CPython raises the `open` audit event for builtins.open, io.open, pathlib's readers and os.open alike, so every read-mode open of the ledger is seen whichever API made it, and each hit names the hook frames that made it.

EVERY POSITIVE HAS ITS CONTROL: with WORKLIST_READ_MEMO=off the same probe counts several reads (it is not blind), and an append between two in-process reads is seen by the second (the memo cannot serve a stale ledger).
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest
import wl_planrec as R

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
        for name, paths in watch.items():
            if p in paths:
                note(name)
    sys.addaudithook(audit)
    sys.argv = [hook]
    sys.path.insert(0, os.path.dirname(hook))
    runpy.run_path(hook, run_name="__main__")
    """
)

REL = "agent/plans/PLAN-hotpath-fixture.md"
PLAN = """# PLAN: hot path fixture
Status: approved -- fixture
Owner: deadbeef
First-Seen: 2026-11-23
Depends-On: no-dep -- fixture
Priority: P1 -- fixture
Concurrency: parallel
Owns: none -- fixture

## Boxes

- [ ] HP1 [writer] The first open box of the fixture plan, read by every plan reader.
  Accept: nothing, it is a fixture.
- [ ] HP2 [writer] The second open box of the fixture plan, also open.
  Accept: nothing, it is a fixture.
"""


def ledger(fix: wlfix.Fixture):
    return R.investigation_path(fix.proj)


def world(fix: wlfix.Fixture) -> None:
    """A store item, a plan with open boxes, one investigation row per box, and a finished transcript."""
    plan = fix.proj / REL
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(PLAN, encoding="utf-8")
    rows = []
    for _i, _line, _body, sig in R.open_boxes(PLAN):
        rows.append({"plan": REL, "sig": sig, "verdict": "absent", "at": "2026-11-23T00:00:00Z"})
    assert len(rows) == 2, "the fixture plan has no parsable open box"
    path = ledger(fix)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    got = fix.cli("--add", wlfix.ME, "probe the ledger memo")
    assert got.rc == 0, got.err[-800:]
    fix.say("done\n\n## Remaining\n- the probe item")
    fix.brief_now()
    fix.hand_now()


def counted_stop(fix: wlfix.Fixture, tmp, extra: dict | None = None) -> tuple[dict, wlfix.Result]:
    probe = tmp / "probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    out = tmp / "opens.txt"
    if out.exists():
        out.unlink()
    watch = {"ledger": [str(ledger(fix).resolve())]}
    before = fix._lastevents()
    proc = subprocess.run(
        [sys.executable, str(probe), str(fix.hook), str(out), json.dumps(watch)],
        input=fix.event(),
        capture_output=True,
        text=True,
        env=fix.stop_env(extra),
        check=False,
    )
    counts: dict = {"ledger": 0, "where": []}
    if out.is_file():
        for line in out.read_text(encoding="utf-8").splitlines():
            name, _, where = line.partition(" ")
            counts[name] += 1
            counts["where"].append("%s from %s" % (name, where))
    got = wlfix.Result(proc.stdout, proc.stderr, proc.returncode)
    got.battery_ran = proc.returncode == 0 and fix._lastevents() != before
    return counts, got


# THE FOUR READERS IN ONE PROCESS. A fixture Stop run reaches only the box audit's read; the judge's claim check, the preflight survey and the dependency graph each read the ledger on their own paths. This launcher drives each reader once in one process under the same audit probe, so the count is the number of decodes those four paths cost together.
READERS = textwrap.dedent(
    """
    import json, os, pathlib, sys
    stop, root, rel, sig, out = sys.argv[1:6]
    root = pathlib.Path(root)
    sys.path.insert(0, stop)
    import wl_claimcheck, wl_plandeps, wl_planpreflight, wl_planrec
    ledger = os.path.abspath(str(wl_planrec.investigation_path(root)))
    opens = []
    def audit(ev, args):
        if ev == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            mode = args[1]
            if isinstance(mode, str) and any(c in mode for c in "wax+"):
                return
            if os.path.abspath(os.fsdecode(args[0])) == ledger:
                # The caller of read_investigations names the reader.
                f = sys._getframe(1)
                while f is not None and f.f_code.co_name != "read_investigations":
                    f = f.f_back
                f = f.f_back if f is not None else None
                opens.append(os.path.basename(f.f_code.co_filename) if f else "?")
    sys.addaudithook(audit)
    seen = {}
    seen["claimcheck"] = (wl_claimcheck.investigation_for_claim(root, "closes " + sig) or {}).get("sig")
    seen["preflight"] = [b.verdict for b in wl_planpreflight.survey(root, rel, base="0" * 40)]
    graph = wl_plandeps.Graph({}, "", root=root)
    seen["plandeps"] = graph._present(rel, sig)
    seen["planrec"] = (wl_planrec.investigation_for(root, rel, sig) or {}).get("verdict")
    pathlib.Path(out).write_text(json.dumps({"opens": opens, "seen": seen}), encoding="utf-8")
    """
)


def readers_in_one_process(fix: wlfix.Fixture, tmp, extra: dict | None = None) -> dict:
    script = tmp / "readers.py"
    script.write_text(READERS, encoding="utf-8")
    out = tmp / "readers.json"
    sig = R.open_boxes(PLAN)[0][3]
    env = fix.stop_env(extra)
    proc = subprocess.run(
        [sys.executable, str(script), str(wlfix.STOP_DIR), str(fix.proj), REL, sig, str(out)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    got = json.loads(out.read_text(encoding="utf-8"))
    # Each reader must have SEEN the row, or a count of one would only mean three readers found nothing to read.
    assert got["seen"]["claimcheck"] == sig, got
    assert got["seen"]["preflight"] == ["absent", "absent"], got
    assert got["seen"]["planrec"] == "absent", got
    assert got["seen"]["plandeps"] is False, got
    return got


def test_one_stop_reads_the_ledger_once(wl, tmp_path):
    world(wl)
    counts, got = counted_stop(wl, tmp_path)
    assert got.battery_ran, (
        "the Stop battery did not run, so the count measures nothing: %s" % got.err[-800:]
    )
    # ZERO would mean the probe is blind or no reader ran, not that the hook is fast.
    assert counts["ledger"] == 1, counts


def test_the_four_readers_share_one_decode(wl, tmp_path):
    world(wl)
    got = readers_in_one_process(wl, tmp_path)
    assert len(got["opens"]) == 1, got["opens"]


def test_the_probe_counts_every_reader_with_the_memo_off(wl, tmp_path):
    """CONTROL: WORKLIST_READ_MEMO=off restores a decode per reader, and the same probe then counts all four."""
    world(wl)
    got = readers_in_one_process(wl, tmp_path, {"WORKLIST_READ_MEMO": "off"})
    assert sorted(got["opens"]) == [
        "wl_claimcheck.py",
        "wl_plandeps.py",
        "wl_planpreflight.py",
        "wl_planrec.py",
    ], got["opens"]


@pytest.fixture
def memo(wl, monkeypatch):
    monkeypatch.delenv("WORKLIST_READ_MEMO", raising=False)
    R.clear_investigation_memo()
    world(wl)
    yield wl
    R.clear_investigation_memo()


def _append(fix: wlfix.Fixture, row: dict) -> None:
    with ledger(fix).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def test_an_append_between_two_reads_is_seen(memo):
    """CONTROL for the memo: the second read is served when the ledger did not move, and the next read after an append sees the new row."""
    first = R.read_investigations(memo.proj)
    again = R.read_investigations(memo.proj)
    assert again == first
    assert len(first) == 2
    assert R.INVESTIGATION_MEMO_STATS == {"hit": 1, "miss": 1}
    _append(
        memo, {"plan": REL, "sig": "feedf00d", "verdict": "present", "at": "2026-11-23T01:00:00Z"}
    )
    third = R.read_investigations(memo.proj)
    assert [r["sig"] for r in third][-1] == "feedf00d", third
    assert R.INVESTIGATION_MEMO_STATS["miss"] == 2


def test_a_served_row_is_a_copy(memo):
    """A caller mutating its rows cannot change what the next caller is served."""
    rows = R.read_investigations(memo.proj)
    rows[0]["verdict"] = "MUTATED"
    rows.append({"sig": "zz"})
    again = R.read_investigations(memo.proj)
    assert [r["verdict"] for r in again] == ["absent", "absent"]


def test_a_missing_ledger_is_empty_and_not_remembered(memo):
    """A failed read answers [] and stores nothing, so the ledger appearing later is read."""
    ledger(memo).unlink()
    assert R.read_investigations(memo.proj) == []
    _append(memo, {"plan": REL, "sig": "feedf00d", "verdict": "absent"})
    assert [r["sig"] for r in R.read_investigations(memo.proj)] == ["feedf00d"]
