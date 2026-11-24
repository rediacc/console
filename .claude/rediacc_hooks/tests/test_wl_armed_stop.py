"""Armed actions, the Stop check and its wiring (agent/plans/PLAN-armed-actions.md box AA3).

Every positive has its control in the same case: an arm blocks once its trigger holds and is silent one step before; an armed lease stands the unlanded block down and the same lease unarmed or with an expired arm blocks; a fired DEFER-CLOSED arm takes over the deferral's demand and hands it back once started; an unfired arm with no timer asks for one and is quiet with one. Each case fails on the code before AA3, which had no `armed-actions` segment, no lease cover and no arm-aware wake-up.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import subprocess
import time
import types

import pytest

from rediacc_hooks.tests import wlfix

ME = wlfix.ME
SID = wlfix.SID
A = wlfix.import_wl("wl_armed")
CK = wlfix.import_wl("wl_checks")
M = wlfix.import_wl("worklist_messages")
SD = wlfix.import_wl("wl_standdown")
WT = wlfix.import_wl("wl_worktrees")
EFFORT = wlfix.import_wl("wl_effort")

DUE = "ARMED ACTION DUE"
SAID = "held work armed\n\n## Remaining\n- the held start waits on its trigger"


def utc(minutes=0):
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=minutes)


def stamp(minutes=0):
    return A.stamp(utc(minutes))


def plant(wl, **ev):
    """Append one event as another writer would."""
    ev.setdefault("at", stamp())
    ev.setdefault("by", ME)
    ev.setdefault("ns", time.time_ns())
    with (wl.store_dir / "zz-planted.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(ev) + "\n")


def plant_item(wl, rid, text, state=" ", at_min=-2000):
    plant(wl, ev="add", id=rid, at=stamp(at_min), s=state, o=ME, t="%s (%s)" % (text, ME))


def plant_arm(wl, rid, when, at_min=-10, exp_h=24, cmd="./run.sh worktree land L1", run=""):
    at = stamp(at_min)
    aid = A.arm_id(rid, at, list(when))
    plant(
        wl,
        ev="arm",
        id=rid,
        at=at,
        aid=aid,
        when=list(when),
        run=run,
        cmd="" if run else cmd,
        sha="",
        lease="",
        exp=A.stamp(utc(at_min) + datetime.timedelta(hours=exp_h)),
    )
    return aid


def stop(wl):
    wl.newturn()
    wl.say(SAID)
    return wl.run()


def full(wl, needle, tries=5):
    """The first stop whose output quotes `needle`. A block quotes one check in full and names the rest by their first words, rotating, so the armed block may take a stop or two to come round; every stop on the way must at least name it."""
    for _ in range(tries):
        got = stop(wl)
        assert DUE in got.out, got.out[:2000]
        if needle in got.out:
            return got
    raise AssertionError("%r never quoted in %d stops; last: %s" % (needle, tries, got.out[:2500]))


def due_block(out):
    """The armed block's own text, from its header to the end of the reason."""
    return json.loads(out)["reason"].split(DUE, 1)[1]


@pytest.fixture
def ready(wl):
    wl.brief_now()
    wl.hand_now()
    return wl


# ---------------------------------------------------------------------------- (a) TICKED


def test_a_ticked_arm_is_silent_while_the_blocker_is_open_blocks_after_the_tick_and_goes_quiet_after_start(
    ready,
):
    wl = ready
    plant_item(wl, "aaaa0001", "land the held lease")
    plant_item(wl, "bbbb0002", "the blocker")
    plant_arm(wl, "aaaa0001", ["TICKED:#bbbb0002"])
    got = stop(wl)
    assert DUE not in got.out, got.out[:1200]

    plant(wl, ev="state", id="bbbb0002", s="x", note="done: commit:abc1234")
    got = full(wl, "--armed-start %s aaaa0001" % ME)
    block = due_block(got.out)
    assert "./run.sh worktree land L1" in block, block
    assert "TICKED:#bbbb0002: #bbbb0002 is [x]" in block, block
    fires = [
        e
        for e in map(json.loads, wl.wl_events().splitlines())
        if e.get("ev") == "armfire" and e.get("id") == "aaaa0001"
    ]
    assert [f["v"] for f in fires] == ["fired"], fires

    # The latch is a store event: the next stop names it again without re-judging, and appends no second latch.
    got = stop(wl)
    assert DUE in got.out, got.out[:2000]
    started = wl.cli("--armed-start", ME, "aaaa0001")
    assert started.rc == 0, started.err
    got = stop(wl)
    assert DUE not in got.out, got.out[:2000]
    fires = [
        e
        for e in map(json.loads, wl.wl_events().splitlines())
        if e.get("ev") == "armfire" and e.get("id") == "aaaa0001"
    ]
    assert len(fires) == 1, fires


# ---------------------------------------------------------------------------- (b) NOT-BEFORE


def test_b_not_before_is_silent_a_minute_before_and_blocks_at_the_instant(ready):
    wl = ready
    plant_item(wl, "cccc0003", "start the dated step")
    plant_arm(wl, "cccc0003", ["NOT-BEFORE:%s" % stamp(1)], at_min=-30)
    got = stop(wl)
    assert DUE not in got.out, got.out[:1200]

    plant_item(wl, "dddd0004", "start the dated step now")
    plant_arm(wl, "dddd0004", ["NOT-BEFORE:%s" % stamp(0)], at_min=-30)
    got = full(wl, "--armed-start %s dddd0004" % ME)
    block = due_block(got.out)
    assert block.startswith(": 1 held start(s)"), block
    assert "#cccc0003" not in block, block


def test_expired_and_void_arms_block_and_name_the_disarm(ready):
    wl = ready
    plant_item(wl, "eeee0005", "a hold whose trigger never came")
    plant_arm(wl, "eeee0005", ["NOT-BEFORE:%s" % stamp(600)], at_min=-1500, exp_h=1)
    plant_item(wl, "ffff0006", "a hold on a dropped blocker")
    plant_item(wl, "ffff0007", "the dropped blocker", state="~")
    plant_arm(wl, "ffff0006", ["TICKED:#ffff0007"])
    got = full(wl, "EXPIRED before every token held")
    block = due_block(got.out)
    assert "VOID, its trigger can never fire" in block, block
    assert "--disarm %s eeee0005" % ME in block, block
    assert "--disarm %s ffff0006" % ME in block, block
    assert "--armed-start %s" % ME not in block, block


# ---------------------------------------------------------------------------- (c) the lease cover


def _lease_world(monkeypatch):
    """One finished lease L1 of this session with one unlanded commit, read without git."""
    world = {
        "leases": {"L1": {"console": "/x"}},
        "tips": {},
        "pins": {},
        "records": {"L1": {"owner": ME, "path": "/nonexistent/L1", "base": {}}},
        "holds": {},
        "dirs": [],
        "doubts": [],
    }
    monkeypatch.setattr(WT, "read_world", lambda _root: world)
    monkeypatch.setattr(WT, "_record_orphans", lambda _w, _t: [])
    monkeypatch.setattr(WT, "_holder", lambda *_a: "")
    monkeypatch.setattr(WT, "signature", lambda *_a: "sig")
    monkeypatch.setattr(WT, "figures", lambda *_a: {"dirty": 0, "commits": {"console": ["a" * 40]}})
    monkeypatch.setattr(WT.wl_scratch, "lease_texts", lambda _items: {})
    monkeypatch.setattr(WT.wl_scratch, "process_cwds", list)
    monkeypatch.setattr(WT.C, "landing_record", lambda _root: None)


def _drive_worktree(monkeypatch, items):
    notes, blocks = [], []
    monkeypatch.setattr(CK, "vm_check_running", lambda *_a: False)
    monkeypatch.setattr(CK, "release_local_running", lambda *_a: False)
    monkeypatch.setattr(CK, "green_receipt_on_unpushed_head", lambda *_a: False)
    monkeypatch.setattr(
        CK, "outq_add", lambda _w, _s, _st, _k, text, _p, **_kw: notes.append(text) or True
    )
    monkeypatch.setattr(WT, "live_work", lambda *_a: {"ids": set(), "trees": set(), "cwd": ""})
    CK.worktree_check(
        None,
        SID,
        {},
        types.SimpleNamespace(items=items),
        None,
        {"cwd": "/nonexistent", "session_id": SID},
        lambda key, *_a, **_kw: blocks.append(key),
    )
    return notes, blocks


def _held(arm=None):
    rec = {"id": "aaaa1111", "owner": ME, "state": " ", "text": "land L1", "line": "land L1"}
    if arm is not None:
        rec["arm"] = arm
    return rec


def _arm(**kw):
    base = {
        "aid": "1234abcd",
        "when": ["CI-QUICK:done"],
        "at": stamp(-10),
        "exp": stamp(600),
        "lease": "L1",
        "verdict": "",
        "started_at": "",
    }
    base.update(kw)
    return base


def test_c_an_armed_lease_is_listed_armed_and_the_same_lease_unarmed_or_expired_blocks(monkeypatch):
    _lease_world(monkeypatch)
    notes, blocks = _drive_worktree(monkeypatch, [_held(_arm())])
    assert blocks == [], blocks
    assert any(n.startswith(M.N_WORKTREE_ARMED.split("%s")[0]) and "L1" in n for n in notes), notes
    assert any("armed on #aaaa1111 (aid 1234abcd, armed)" in n for n in notes), notes

    # CONTROL: the same lease with no arm blocks.
    notes, blocks = _drive_worktree(monkeypatch, [_held()])
    assert blocks == ["worktree-unlanded"], blocks
    # CONTROL: an arm past its expiry covers nothing.
    notes, blocks = _drive_worktree(monkeypatch, [_held(_arm(exp=stamp(-1)))])
    assert blocks == ["worktree-unlanded"], blocks
    # CONTROL: an arm naming another lease covers nothing here.
    notes, blocks = _drive_worktree(monkeypatch, [_held(_arm(lease="L2"))])
    assert blocks == ["worktree-unlanded"], blocks
    # CONTROL: a started arm covers nothing.
    notes, blocks = _drive_worktree(monkeypatch, [_held(_arm(started_at=stamp(-1)))])
    assert blocks == ["worktree-unlanded"], blocks


def test_c_a_fired_arm_covers_only_while_the_armed_block_blocks(monkeypatch):
    """Design 6: exactly one check blocks at every level. A fired arm hands the lease to `armed-action-due` at `smart` and above; below it the unlanded block speaks."""
    _lease_world(monkeypatch)
    fired = _arm(verdict="fired", why="CI-QUICK:done: ...")
    EFFORT.activate("high")
    try:
        _notes, blocks = _drive_worktree(monkeypatch, [_held(dict(fired))])
        assert blocks == [], blocks
        EFFORT.activate("low")
        _notes, blocks = _drive_worktree(monkeypatch, [_held(dict(fired))])
        assert blocks == ["worktree-unlanded"], blocks
    finally:
        EFFORT.activate(None)


# ---------------------------------------------------------------------------- (d) the stand-down class


def test_d_pr_loop_keeps_armed_action_due_and_the_landing_tree_parks_it():
    assert "armed-action-due" in SD._BUILD_ONLY
    assert SD.keeps(SD.PR_LOOP, "armed-action-due", False, False)
    assert "armed-action-due" not in SD.PARKED_BY_DESIGN
    # CONTROL: the landing tree finishes and does not start (ruling B2).
    assert not SD.keeps(SD.LANDING_TREE, "armed-action-due", False, False)
    table = EFFORT.load()[0]
    assert table["checks"]["armed-action-due"] == {"block": "smart", "advise": "low"}
    assert EFFORT.verdict("armed-action-due", "smart", table) == EFFORT.BLOCK
    assert EFFORT.verdict("armed-action-due", "low", table) == EFFORT.ADVISE
    assert EFFORT.verdict("armed-action-due", "quiet", table) == EFFORT.OFF


def test_d_the_segment_is_registered_after_defer_expired_and_tiered_at_mission():
    registry = wlfix.import_wl("wl_stopregistry")
    keys = [s.key for s in registry.REGISTRY]
    assert keys.index("armed-actions") == keys.index("defer-expired") + 1
    assert CK.check_tier("armed-action-due") == CK.T_MISSION


# ---------------------------------------------------------------------------- (e) the rotation-lease replay


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A checkout with a bare upstream, one pushed commit and one commit on top of it."""
    bare = tmp_path / "up.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    _git(work, "config", "user.email", "t@example.org")
    _git(work, "config", "user.name", "t")
    (work / "a").write_text("1", encoding="utf-8")
    _git(work, "add", "a")
    _git(work, "commit", "-q", "-m", "one")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-q", "-u", "origin", "main")
    (work / "a").write_text("2", encoding="utf-8")
    _git(work, "commit", "-q", "-am", "two")
    (work / ".ci" / "cache").mkdir(parents=True)
    return work


@pytest.fixture
def store(tmp_path, monkeypatch):
    store_mod = wlfix.import_wl("wl_store")
    monkeypatch.setenv("WORKLIST_STORE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    (tmp_path / "store").mkdir()
    (tmp_path / "tmp").mkdir()
    worklist = tmp_path / "tmp" / "wl.md"
    worklist.write_text("", encoding="utf-8")
    return store_mod, worklist


def _receipt(repo, finished, code=0):
    doc = {
        "exitCode": code,
        "whole": True,
        "headTree": _git(repo, "rev-parse", "HEAD^{tree}"),
        "head": _git(repo, "rev-parse", "HEAD"),
        "finishedAt": finished,
    }
    (repo / ".ci" / "cache" / "prepush-receipt.json").write_text(json.dumps(doc), encoding="utf-8")


def _segment(st, worklist, repo, state_doc):
    """Run the real `armed-actions` segment over the store and return the keys and texts it raised."""
    fold = st.load(worklist, sync=False)
    raised = []
    ns = {
        "me8": ME,
        "root": repo,
        "vadd": lambda key, _always, text, **_kw: raised.append((key, text)),
        "worklist": worklist,
        "session_id": SID,
        "fold": fold,
        "event": {"session_id": SID, "background_tasks": []},
        "state_doc": state_doc,
    }
    CK._stop_armed_actions(ns)
    return raised


def test_e_the_rotation_lease_hold_replays_silent_during_ci_quick_and_blocks_on_its_receipt(
    repo, store
):
    st, worklist = store
    (rid,) = st.add_items(worklist, ME, ["land the rotation fix lease (%s)" % ME], owner=ME)
    st.arm_item(
        worklist,
        ME,
        rid,
        ["CI-QUICK:done"],
        cmd="./run.sh worktree land rot-1",
        lease="rot-1",
        exp=stamp(600),
    )
    state_doc: dict = {}
    # ci:quick still running: the only receipt on disk predates the arm.
    _receipt(repo, stamp(-30))
    assert _segment(st, worklist, repo, state_doc) == []
    # CONTROL: no receipt at all is silent too.
    (repo / ".ci" / "cache" / "prepush-receipt.json").unlink()
    assert _segment(st, worklist, repo, state_doc) == []

    # The run finishes green after the arm, HEAD unpushed: the block names the command with the push first.
    _receipt(repo, stamp(1))
    raised = _segment(st, worklist, repo, state_doc)
    assert [k for k, _t in raised] == ["armed-action-due"], raised
    text = raised[0][1]
    assert "./run.sh worktree land rot-1" in text, text
    assert "git push first" in text, text
    assert text.index("git push first") < text.index("--armed-start %s %s" % (ME, rid)), text
    assert "CI-QUICK:done: prepush-receipt.json finishedAt=" in text, text


def test_e_a_red_receipt_fires_done_without_the_push_prefix(repo, store):
    """CONTROL for the push prefix: CI-QUICK:done fires whatever the exit code, and a red receipt owes no push."""
    st, worklist = store
    (rid,) = st.add_items(worklist, ME, ["land after the run (%s)" % ME], owner=ME)
    st.arm_item(
        worklist,
        ME,
        rid,
        ["CI-QUICK:done"],
        cmd="./run.sh worktree land rot-2",
        exp=stamp(600),
    )
    _receipt(repo, stamp(1), code=1)
    raised = _segment(st, worklist, repo, {})
    assert [k for k, _t in raised] == ["armed-action-due"], raised
    assert "exitCode=1" in raised[0][1], raised
    assert "git push first" not in raised[0][1], raised


def test_e_a_run_brief_that_changed_since_the_arm_is_named(repo, store):
    st, worklist = store
    (rid,) = st.add_items(worklist, ME, ["start the briefed writer (%s)" % ME], owner=ME)
    brief = pathlib.Path(A.brief_rel(ME, rid))
    (repo / brief).parent.mkdir(parents=True)
    (repo / brief).write_text(A.start_line(ME, rid) + "\nbrief\n", encoding="utf-8")
    sha = A.brief_sha(repo / brief)
    st.arm_item(worklist, ME, rid, ["CI-QUICK:done"], run=str(brief), sha=sha, exp=stamp(600))
    _receipt(repo, stamp(1))
    _git(repo, "add", str(brief))
    _git(repo, "commit", "-q", "-m", "brief")
    raised = _segment(st, worklist, repo, {})
    assert "BRIEF" not in raised[0][1], raised
    assert "then: cat %s" % brief in raised[0][1], raised
    # The brief rewritten after the arm: the block says so and names the re-arm.
    (repo / brief).write_text(A.start_line(ME, rid) + "\nrewritten\n", encoding="utf-8")
    raised = _segment(st, worklist, repo, {})
    assert "BRIEF %s changed since the arm" % brief in raised[0][1], raised


# ---------------------------------------------------------------------------- defer-expired


def test_a_fired_defer_closed_arm_takes_over_the_deferral_and_hands_it_back_after_start(ready):
    wl = ready
    plant(
        wl,
        ev="add",
        id="9999aaaa",
        at=stamp(-130),
        s="?",
        o=ME,
        t="keep the flag? DEFAULT: keep it (%s)" % ME,
    )
    got = stop(wl)
    assert "OUTLIVED their autonomy window" in got.out, got.out[:1500]

    plant_item(wl, "8888bbbb", "apply the legal default")
    plant_arm(wl, "8888bbbb", ["DEFER-CLOSED:#9999aaaa"], at_min=-125)
    got = stop(wl)
    assert DUE in got.out, got.out[:2000]
    assert "OUTLIVED their autonomy window" not in got.out, got.out[:2000]

    assert wl.cli("--armed-start", ME, "8888bbbb").rc == 0
    got = stop(wl)
    assert DUE not in got.out, got.out[:2000]
    assert "OUTLIVED their autonomy window" in got.out, got.out[:2000]


# ---------------------------------------------------------------------------- (f) wake-timer


def test_f_an_unfired_arm_with_no_waker_raises_wake_timer_and_a_waker_silences_it(ready):
    wl = ready
    wl.waker = False
    got = stop(wl)
    assert "NO WAKE-UP TIMER" not in got.out, got.out[:1200]

    plant_item(wl, "7777cccc", "start after the window")
    plant_arm(wl, "7777cccc", ["NOT-BEFORE:%s" % stamp(120)])
    got = stop(wl)
    assert "NO WAKE-UP TIMER: 1 armed action(s)" in got.out, got.out[:2000]
    assert "#7777cccc on NOT-BEFORE:" in got.out, got.out[:2000]
    assert "wl_wake.py deadbeef --minutes 30" in got.out, got.out[:2000]

    # CONTROL: the session's timer is running.
    wl.bg = json.dumps([dict(wlfix.WAKER_TASK)])
    got = stop(wl)
    assert "NO WAKE-UP TIMER" not in got.out, got.out[:2000]


def test_f_a_fired_arm_needs_no_timer(ready):
    """CONTROL: only an arm still waiting asks for a wake-up; one whose trigger held this stop is named by the armed block instead."""
    wl = ready
    wl.waker = False
    plant_item(wl, "6666dddd", "start now")
    plant_arm(wl, "6666dddd", ["NOT-BEFORE:%s" % stamp(0)], at_min=-30)
    got = stop(wl)
    assert DUE in got.out, got.out[:2000]
    assert "NO WAKE-UP TIMER" not in got.out, got.out[:2000]


# ---------------------------------------------------------------------------- STATE.md `unarmed`


def test_a_live_arm_with_no_armed_section_reads_unarmed_and_naming_it_clears(ready):
    wl = ready
    got = stop(wl)
    assert "no '## Armed' section" not in got.out, got.out[:1500]
    plant_item(wl, "5555eeee", "a held landing")
    plant_arm(wl, "5555eeee", ["NOT-BEFORE:%s" % stamp(120)])
    wl.bg = json.dumps([dict(wlfix.WAKER_TASK)])
    got = stop(wl)
    assert "unarmed" in got.out, got.out[:2500]
    assert "no '## Armed' section" in got.out, got.out[:2500]

    body = wlfix.STATE_BODY + "\n\n## Armed\n\n- #5555eeee lands L1 at the window."
    assert wl.python(["--state", ME], stdin=body).rc == 0
    got = stop(wl)
    assert "no '## Armed' section" not in got.out, got.out[:2500]


def test_the_unarmed_verdict_is_explained_and_counts_toward_compaction():
    assert "## Armed" in CK._agent_state_because("unarmed", 5)
    assert "unarmed" in CK._COMPACTION_ASTATES
