"""The retirement and merge report over the guard chain ledger, and the two-way hook budgets (agent/plans/PLAN-tooling-code-reduction.md CR8, design D6).

Every question the report answers has a fixture that must be NAMED and a control that must stay silent: a never-fired guard against one that fired inside the window, an often-fired unconfirmed rule against the same rule once confirmed, and two overlapping twins against two guards that fire apart. A window shorter than the verdict's days is printed as a window, never as a verdict.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import types

import pytest
import wl_hookreport as H
import wl_resprofile
import wl_ressample
import wl_retro
import wl_trapfires

from rediacc_hooks import dispatch

NOW = datetime.datetime(2026, 11, 23, 12, 0, 0, tzinfo=datetime.UTC)
GUARDS = {
    "block_quiet": "pre-bash",
    "block_loud": "pre-bash",
    "block_twin_edit": "pre-edit",
    "block_twin_shell": "pre-bash",
    "block_apart": "pre-bash",
    "warn_note": "post-bash",
}


def stamp(days_ago: float, minute: int = 0) -> str:
    when = NOW - datetime.timedelta(days=days_ago) + datetime.timedelta(minutes=minute)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def row(ts: str, refused_by=None, session="s1", chain="pre-bash", ms=50.0, slow=()):
    return {
        "chain": chain,
        "refused_by": refused_by,
        "rc": 2 if refused_by else 0,
        "ms": ms,
        "slow": [list(p) for p in slow],
        "crashed": [],
        "session": session,
        "ts": ts,
    }


@pytest.fixture
def tree(tmp_path):
    """A checkout with six guard modules, a 15-day ledger and an empty trapguard directory."""
    gdir = tmp_path.joinpath(*H.GUARDS_REL)
    gdir.mkdir(parents=True)
    for stem, chain in GUARDS.items():
        (gdir / ("%s.py" % stem)).write_text(
            'CHAIN = "%s"\nORDER = 1\n\n\ndef run(event):\n    return 0\n' % chain,
            encoding="utf-8",
        )
    (gdir / "_helper.py").write_text("X = 1\n", encoding="utf-8")
    rows = [row(stamp(15))]  # the window opens 15 days back
    rows += [row(stamp(1, i), "block_loud", session="s%d" % i) for i in range(45)]
    # Twins: the edit and the shell half refuse the same (session, minute) three times.
    for i in range(3):
        rows.append(row(stamp(2, i), "block_twin_edit", session="t", chain="pre-edit"))
        rows.append(row(stamp(2, i), "block_twin_shell", session="t"))
    # Apart: fires in other minutes and sessions than anything else.
    rows += [row(stamp(3, 30 + i), "block_apart", session="a%d" % i) for i in range(3)]
    rows.append(row(stamp(0.5), slow=[("block_loud", 80.0)]))
    ledger = tmp_path.joinpath(*H.LEDGER_REL)
    ledger.parent.mkdir(parents=True)
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    trap = tmp_path / "trapguard"
    trap.mkdir()
    return tmp_path, rows, trap


def text_of(tree, **kw):
    root, rows, trap = tree
    return H.report(root, rows=rows, trap_base=trap, receipts=kw.pop("receipts", []), now=NOW)


def section(text: str, head: str) -> str:
    """The lines of one report section, from its heading to the next blank line."""
    start = text.index(head)
    end = text.find("\n\n", start)
    return text[start : end if end != -1 else len(text)]


def test_the_ledger_path_is_the_one_dispatch_writes():
    assert H.LEDGER_REL == dispatch.LEDGER_REL


def test_a_never_fired_guard_is_named_and_a_fired_one_is_not(tree):
    text = text_of(tree)
    part = section(text, "never fired in 14 days")
    assert "block_quiet" in part, text
    # CONTROLS: a guard that refused inside the window, and a warn_ guard (it never refuses).
    assert "block_loud" not in part
    assert "block_twin_edit" not in part
    assert "warn_note" not in part


def test_a_short_window_is_not_a_verdict(tree):
    root, rows, trap = tree
    recent = [r for r in rows if r["ts"] >= stamp(3)]
    text = H.report(root, rows=recent, trap_base=trap, receipts=[], now=NOW)
    assert "NOT a 14-day verdict" in text, text
    assert "never fired in 14 days" not in text


def test_an_often_fired_unconfirmed_rule_is_named_until_confirmed(tree):
    trap = tree[2]
    head = "fired more than %d times" % H.RETIRE_FIRES
    assert "block_loud" in section(text_of(tree), head)
    # The same rule, once confirmed through the shared ledger, leaves the list: the CONTROL.
    wl_trapfires.confirm("block_loud", trap)
    assert "block_loud" not in section(text_of(tree), head)


def test_a_trapguard_rule_counts_through_the_same_rule(tree):
    trap = tree[2]
    (trap / "fires.jsonl").write_text(
        "".join(json.dumps({"rule": "trap_x", "ts": stamp(1)}) + "\n" for _ in range(41)),
        encoding="utf-8",
    )
    assert "trap_x" in section(text_of(tree), "fired more than")
    assert wl_trapfires.retire_candidates(trap) == [("trap_x", 41)]


def test_overlapping_twins_are_named_and_guards_firing_apart_are_not(tree):
    text = text_of(tree)
    part = section(text, "overlapping fire sets")
    assert "block_twin_edit + block_twin_shell: 3 shared" in part, text
    assert "block_apart" not in part
    assert "block_loud" not in part


def test_slow_guards_and_owed_stop_timing_are_printed(tree):
    text = text_of(tree)
    assert "block_loud" in section(text, "slow guards")
    assert "Stop-check timing: UNMEASURED" in text
    assert "SP3" in text


def test_quiet_gates_need_runs_and_no_failure():
    receipts = [{"gates": {"a": 1, "b": 1}, "failed": []} for _ in range(5)]
    receipts.append({"gates": {"a": 1, "b": 1}, "failed": ["b"]})
    costs = {"gates": {"a": {"cpu_s": 3.0}, "b": {"cpu_s": 9.0}}}
    assert H.quiet_gates(receipts, costs) == [("a", 6, 3.0)]
    assert H.quiet_gates(receipts[:4], costs) == [], "four runs are under the floor"


def test_the_snapshot_carries_every_guard_and_no_session(tree):
    root, rows, _trap = tree
    doc = H.snapshot(rows, H.inventory(root), now=NOW)
    assert set(doc["guards"]) == set(GUARDS)
    assert doc["guards"]["block_quiet"]["fires"] == 0
    assert doc["window"]["rows"] == len(rows)
    assert "s1" not in json.dumps({k: v for k, v in doc.items() if k != "window"})
    assert H.check_snapshot(doc, H.inventory(root), now=NOW) == []


def test_the_snapshot_check_refuses_age_drift_and_emptiness(tree):
    root, rows, _trap = tree
    inv = H.inventory(root)
    doc = H.snapshot(rows, inv, now=NOW - datetime.timedelta(days=15))
    stale = H.check_snapshot(doc, inv, now=NOW)
    assert [k for k, _t in stale] == ["hook-ledger:stale"]
    # 0906c47c.2: the finding's text still says why it is stale.
    assert "is more than 14 days old" in stale[0][1], stale
    doc = H.snapshot(rows, inv, now=NOW)
    inv2 = dict(inv, block_new={"chain": "pre-bash", "lines": 3})
    assert [k for k, _t in H.check_snapshot(doc, inv2, now=NOW)] == [
        "hook-ledger:unsnapshotted:block_new"
    ]
    with pytest.raises(H.ReportError):
        H.snapshot([], inv)


def test_the_snapshot_check_prints_freshness_finding_keys(tree, capsys):
    """The CLI prints one `::finding::` key per finding and exits 1, the shape freshness --check carries; a fresh snapshot prints none and exits 0."""
    root, rows, _trap = tree
    path = root.joinpath(*H.SNAPSHOT_REL)
    path.parent.mkdir(parents=True, exist_ok=True)
    stale = H.snapshot(rows, H.inventory(root), now=NOW - datetime.timedelta(days=30))
    path.write_text(json.dumps(stale), encoding="utf-8")
    assert H.main(["--check-snapshot"], root) == 1
    assert "::finding::hook-ledger:stale" in capsys.readouterr().out
    fresh = H.snapshot(rows, H.inventory(root))
    path.write_text(json.dumps(fresh), encoding="utf-8")
    assert H.main(["--check-snapshot"], root) == 0
    assert "::finding::" not in capsys.readouterr().out


def budgets(ceiling=100, slack=0.2):
    return {t: {"slack": slack, "max": {"block_x": ceiling}} for t in H.TABLES}


def measured(value=95):
    return {t: {"block_x": value} for t in H.TABLES}


def test_budgets_hold_in_both_directions():
    assert H.budget_findings(budgets(), measured()) == [], "CONTROL: inside every budget"
    got = measured()
    got["guardLines"] = {"block_x": 101}
    assert any("guardLines block_x GREW" in f for f in H.budget_findings(budgets(), got))
    got["guardLines"] = {"block_x": 70}
    assert any("guardLines block_x SHRANK" in f for f in H.budget_findings(budgets(), got))


def test_budgets_refuse_an_empty_table_and_a_coverage_gap():
    empty = budgets()
    empty["guardLines"] = {"slack": 0.2, "max": {}}
    assert any(
        "guardLines.max is missing or empty" in f for f in H.budget_findings(empty, measured())
    )
    got = measured()
    got["guardLines"] = {"block_x": 95, "block_new": 10}
    assert any("block_new has no budget" in f for f in H.budget_findings(budgets(), got))


def test_write_budgets_lowers_and_adds_and_never_raises():
    got = measured(50)
    got["guardLines"] = {"block_x": 50, "block_new": 10}
    block, added = H.write_budgets(budgets(), got)
    assert block["guardLines"]["max"] == {"block_x": 55, "block_new": 11}
    assert added == ["guardLines block_new"]
    with pytest.raises(H.ReportError, match="refusing to raise"):
        H.write_budgets(budgets(), measured(120))


def test_a_repin_of_a_small_integer_never_reads_as_shrunk_at_once():
    """a0c83ac9.2: ceil(v * (1 + slack / 2)) alone pins v=1 at 2, which --check-budgets reports SHRANK. Control: a large value still gets its headroom."""
    for v in (1, 2, 3, 4, 5, 9):
        block, _added = H.write_budgets(budgets(ceiling=1000), measured(v))
        pinned = {t: {"slack": 0.2, "max": block[t]["max"]} for t in H.TABLES}
        assert H.budget_findings(pinned, measured(v)) == [], v
    block, _added = H.write_budgets(budgets(ceiling=1000), measured(50))
    assert block["guardLines"]["max"]["block_x"] == 55


def test_the_live_budgets_are_green_and_a_planted_growth_reds():
    """The committed budgets against the committed tree, then one guard's ceiling planted under its measured lines."""
    root = H.CHECKOUT
    baseline = json.loads(root.joinpath(*H.BASELINE_REL).read_text(encoding="utf-8"))
    live = H.measure(root, baseline)
    assert len(live["guardLines"]) >= 50, "the inventory is not seeing the guards"
    assert H.budget_findings(baseline["budgets"], live) == []
    stem, lines = max(live["guardLines"].items(), key=lambda kv: kv[1])
    planted = json.loads(json.dumps(baseline["budgets"]))
    planted["guardLines"]["max"][stem] = lines - 1
    assert any("%s GREW" % stem in f for f in H.budget_findings(planted, live))


def test_the_retro_brief_ends_with_the_report(monkeypatch):
    monkeypatch.setattr(wl_retro.wl_hookreport, "retro_section", lambda: "HOOK REPORT FIXTURE")

    ctx = types.SimpleNamespace(
        retro_live=lambda rows: rows,
        retro_rows=lambda _root: [],
        retro_ordered=lambda *_args: None,
        retro_window_start=lambda *_args, **_kw: None,
    )
    monkeypatch.setitem(wl_retro._CTX, "mod", ctx)
    text = wl_retro.brief("/tmp/none.md", "/tmp", "deadbeef", "early", "abc123")
    assert text.rstrip().endswith("HOOK REPORT FIXTURE")


def test_rotation_rolls_an_oversize_ledger_and_the_report_still_reads_it(tree):
    """CR9: over the cap the live ledger is renamed whole; the history is the archives plus the live file."""
    root, rows, _trap = tree
    live = root.joinpath(*H.LEDGER_REL)
    archive, deleted = H.rotate(root, max_bytes=10, now=NOW)
    assert archive is not None
    assert archive.name == "chains-%s.jsonl" % NOW.strftime("%Y%m%dT%H%M%SZ")
    assert deleted == []
    assert not live.exists()
    assert len(H.read_ledger(root)) == len(rows), "rotation lost rows from the report's view"
    live.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    assert len(H.read_ledger(root)) == len(rows) + 1


def test_rotation_keeps_a_small_ledger_and_drops_only_old_archives(tree):
    """The control: under the cap nothing moves; an archive past keep_days goes and a fresh one stays."""
    root, _rows, _trap = tree
    live = root.joinpath(*H.LEDGER_REL)
    old, fresh = (
        live.with_name("chains-20200101T000000Z.jsonl"),
        live.with_name("chains-20261122T000000Z.jsonl"),
    )
    for p in (old, fresh):
        p.write_text("{}\n", encoding="utf-8")
    os.utime(old, (NOW.timestamp() - 40 * 86400,) * 2)
    os.utime(fresh, (NOW.timestamp() - 86400,) * 2)
    archive, deleted = H.rotate(root, now=NOW)
    assert archive is None
    assert live.exists()
    assert deleted == [old]
    assert fresh.exists()
    assert not old.exists()


def test_rotation_refuses_to_overwrite_an_archive(tree):
    root, _rows, _trap = tree
    live = root.joinpath(*H.LEDGER_REL)
    live.with_name("chains-%s.jsonl" % NOW.strftime("%Y%m%dT%H%M%SZ")).write_text(
        "", encoding="utf-8"
    )
    with pytest.raises(H.ReportError):
        H.rotate(root, max_bytes=10, now=NOW)
    assert live.exists()


def test_rotation_never_overwrites_an_archive_that_appears_after_the_exists_check(
    tree, monkeypatch
):
    """The archive is claimed atomically: an archive of the same second keeps its own bytes.

    THE RACE, PLANTED (19df54c9.2). Every existence check of the archive answers "absent" while the file is there, which is what a second rotation sees when it writes the archive between this one's check and its claim. An exists()-then-rename claim overwrites the archive here; the atomic link refuses it.
    """
    root, _rows, _trap = tree
    live = root.joinpath(*H.LEDGER_REL)
    taken = live.with_name("chains-%s.jsonl" % NOW.strftime("%Y%m%dT%H%M%SZ"))
    taken.write_text("first archive\n", encoding="utf-8")
    real_exists = pathlib.Path.exists
    real_path_exists = os.path.exists
    with monkeypatch.context() as m:
        m.setattr(
            pathlib.Path,
            "exists",
            lambda self, *a, **k: self != taken and real_exists(self, *a, **k),
        )
        m.setattr(os.path, "exists", lambda p: pathlib.Path(p) != taken and real_path_exists(p))
        with pytest.raises(H.ReportError):
            H.rotate(root, max_bytes=10, now=NOW)
    assert taken.read_text(encoding="utf-8") == "first archive\n"
    taken.unlink()  # control: with the name free the roll goes through
    archive, _deleted = H.rotate(root, max_bytes=10, now=NOW)
    assert archive == taken
    assert not live.exists()


def test_rotation_of_a_missing_ledger_is_a_quiet_no_op(tmp_path):
    archive, deleted = H.rotate(tmp_path, max_bytes=10, now=NOW)
    assert (archive, deleted) == (None, [])


def test_the_rotate_verb_prints_what_it_did(tree, capsys):
    root, _rows, _trap = tree
    assert H.main(["--rotate"], root) == 0
    assert "under %d bytes, kept" % H.ROTATE_BYTES in capsys.readouterr().out
    live = root.joinpath(*H.LEDGER_REL)
    live.write_bytes(b"x" * (H.ROTATE_BYTES + 1))  # control: over the cap it rolls
    assert H.main(["--rotate"], root) == 0
    assert "rolled into chains-" in capsys.readouterr().out


def test_read_ledger_rereads_when_a_rotation_lands_between_glob_and_live_read(tree, monkeypatch):
    root, rows, _trap = tree
    real_read = H.read_jsonl
    state = {"rotated": False}

    def racing(path):
        if not state["rotated"] and path == root.joinpath(*H.LEDGER_REL):
            state["rotated"] = True
            H.rotate(root, max_bytes=10, now=NOW)
        return real_read(path)

    monkeypatch.setattr(H, "read_jsonl", racing)
    assert len(H.read_ledger(root)) == len(rows), "rows rolled mid-read were lost"


def test_a_failed_rollup_fold_says_why_on_stderr_and_a_clean_one_is_quiet(monkeypatch, capsys):
    """a66ada74.3: fold_rollup answers False on a failure and names the reason; the control is a fold that answers."""

    def boom():
        raise RuntimeError("fold-injected")

    monkeypatch.setattr(wl_resprofile, "fold", boom)
    assert wl_ressample.fold_rollup() is False
    assert "rollup fold failed (RuntimeError: fold-injected)" in capsys.readouterr().err
    monkeypatch.setattr(wl_resprofile, "fold", lambda: {"ok": 1})
    assert wl_ressample.fold_rollup() is True
    assert capsys.readouterr().err == ""


def _arm_failing_live_unlink(monkeypatch, live, archive_fails):
    real_unlink = pathlib.Path.unlink

    def unlink(self, *a, **k):
        if self == live or (archive_fails and self.name.startswith("chains-")):
            raise PermissionError("planted")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "unlink", unlink)


def test_a_failed_live_unlink_undoes_the_link_and_a_failed_undo_is_still_a_report_error(
    tree, monkeypatch
):
    """19df54c9.4 and 9e34e7c2.2: both names would hold the rows (read twice), so the link is undone; an undo that fails too raises ReportError, never a raw OSError."""
    root, rows, _trap = tree
    live = root.joinpath(*H.LEDGER_REL)
    with monkeypatch.context() as m:
        _arm_failing_live_unlink(m, live, archive_fails=False)
        with pytest.raises(H.ReportError, match="cannot remove"):
            H.rotate(root, max_bytes=10, now=NOW)
    assert list(live.parent.glob(H.ARCHIVE_GLOB)) == []
    assert len(H.read_ledger(root)) == len(rows)
    with monkeypatch.context() as m:
        _arm_failing_live_unlink(m, live, archive_fails=True)
        with pytest.raises(H.ReportError, match="cannot undo the link"):
            H.rotate(root, max_bytes=10, now=NOW)


def test_rotation_falls_back_to_a_rename_without_hard_links_and_survives_a_vanished_live(
    tree, monkeypatch
):
    """19df54c9.6 and 19df54c9.1: os.link unsupported (OSError) rolls by rename; a live ledger gone after the size check is a no-op."""
    root, rows, _trap = tree
    live = root.joinpath(*H.LEDGER_REL)

    def nolink(*_a):
        raise OSError("no hard links")

    with monkeypatch.context() as m:
        m.setattr(os, "link", nolink)
        archive, _deleted = H.rotate(root, max_bytes=10, now=NOW)
    assert archive is not None
    assert archive.exists()
    assert not live.exists()
    assert len(H.read_ledger(root)) == len(rows)

    def gone(*_a):
        raise FileNotFoundError("rolled by a peer")

    live.write_text("x" * 50, encoding="utf-8")
    with monkeypatch.context() as m:
        m.setattr(os, "link", gone)
        archive, _deleted = H.rotate(root, max_bytes=10, now=NOW + datetime.timedelta(seconds=5))
    assert archive is None
