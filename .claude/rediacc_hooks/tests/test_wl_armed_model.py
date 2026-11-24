"""Armed actions, the event model and the evaluator (agent/plans/PLAN-armed-actions.md box AA1).

Each positive has its control: a token fires on its artifact NEWER than the arm and stays unfired on the same artifact OLDER than the arm; an arm survives compaction only because the snapshot carries `am` (the control strips it and the arm is gone); a duplicate latch and a stale-`aid` start change nothing; a `[x]` in the working tree does not fire `BOX:` until it is committed.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import subprocess
import types

import pytest
import wl_armed as A
import wl_core as C
import wl_store as S

ME = "cafe0003"
T0 = datetime.datetime(2026, 11, 24, 6, 0, 0, tzinfo=datetime.UTC)


def at(minutes):
    return A.stamp(T0 + datetime.timedelta(minutes=minutes))


def arm_of(when, at_min=0, exp_h=24, **kw):
    base = {
        "aid": "0123abcd",
        "when": list(when),
        "at": at(at_min),
        "exp": A.stamp(T0 + datetime.timedelta(hours=exp_h)),
        "verdict": "",
        "started_at": "",
    }
    base.update(kw)
    return base


def ctx(now_min=60, **kw):
    return A.Ctx(
        root=pathlib.Path("/nonexistent"),
        now=T0 + datetime.timedelta(minutes=now_min),
        by_id=kw.pop("by_id", {}),
        **kw,
    )


def world(now=T0, **kw):
    return A.ArmWorld(root=pathlib.Path("/nonexistent"), now=now, by_id=kw.pop("by_id", {}), **kw)


# ---------------------------------------------------------------------------- NOT-BEFORE


def test_not_before_is_unfired_one_minute_before_and_fired_at_the_instant():
    instant = T0 + datetime.timedelta(hours=2)
    arm = arm_of(["NOT-BEFORE:%s" % A.stamp(instant)])
    before = A.evaluate(arm, ctx(now_min=119))
    assert before[0] == A.ARMED, before
    fired = A.evaluate(arm, ctx(now_min=120))
    assert fired[0] == A.FIRED, fired
    assert "NOT-BEFORE" in fired[1]


def test_not_before_eight_days_out_is_refused_and_six_days_is_accepted():
    far = A.stamp(T0 + datetime.timedelta(days=8))
    with pytest.raises(A.TokenError, match="more than 7 days"):
        A.parse_when(["NOT-BEFORE:%s" % far], world())
    near = A.stamp(T0 + datetime.timedelta(days=6))
    assert A.parse_when(["NOT-BEFORE:%s" % near], world()) == ["NOT-BEFORE:%s" % near]


def test_not_before_in_the_past_or_malformed_is_refused():
    with pytest.raises(A.TokenError, match="not in the future"):
        A.parse_when(["NOT-BEFORE:%s" % A.stamp(T0)], world())
    with pytest.raises(A.TokenError, match="not a YYYY"):
        A.parse_when(["NOT-BEFORE:tomorrow"], world())


# ---------------------------------------------------------------------------- event tokens: newer fires, older holds


def test_reported_fires_on_a_hook_report_newer_than_the_arm_only():
    agent = "a0123456789abcdef"
    rid = agent[-12:]
    arm = arm_of(["REPORTED:%s" % agent], at_min=10)
    old = [{"id": rid, "at": at(5), "src": "hook"}]
    assert A.evaluate(arm, ctx(reports=lambda: old))[0] == A.ARMED
    forged = [{"id": rid, "at": at(20), "src": "scan"}]
    assert A.evaluate(arm, ctx(reports=lambda: forged))[0] == A.ARMED
    new = [*old, {"id": rid + "-2", "at": at(20), "src": "hook"}]
    verdict, why = A.evaluate(arm, ctx(reports=lambda: new))
    assert verdict == A.FIRED
    assert rid + "-2" in why


def test_reported_at_arm_time_needs_a_meta_in_this_session():
    w = world(agents={"a0123456789abcdef"})
    assert A.parse_when(["REPORTED:a0123456789abcdef"], w) == ["REPORTED:a0123456789abcdef"]
    with pytest.raises(A.TokenError, match="no meta"):
        A.parse_when(["REPORTED:affffffffffffffff"], w)
    with pytest.raises(A.TokenError, match="unreadable"):
        A.parse_when(["REPORTED:a0123456789abcdef"], world(agents=None, agents_why="gone"))


def test_reported_item_reference_resolves_to_the_lease_worker():
    by_id = {"beef1234": {"id": "beef1234", "state": ">", "worker": "a0123456789abcdef"}}
    w = world(by_id=by_id, agents={"a0123456789abcdef"})
    assert A.parse_when(["REPORTED:#beef1234"], w) == ["REPORTED:a0123456789abcdef"]
    by_id["beef1234"]["worker"] = ""
    with pytest.raises(A.TokenError, match="no worker"):
        A.parse_when(["REPORTED:#beef1234"], w)


def test_exit_fires_only_after_it_was_seen_running_and_is_gone_from_event_and_proc():
    arm = arm_of(["EXIT:b1234567"], at_min=0)
    seen = {}
    A.note_running(seen, [({}, arm)], {"b1234567"}, T0 + datetime.timedelta(minutes=1))
    assert seen == {"0123abcd": ["b1234567"]}
    # Still running: held.
    assert A.evaluate(arm, ctx(running={"b1234567"}, seen=seen))[0] == A.ARMED
    # Gone from the event but a process still writes its output: held.
    assert (
        A.evaluate(arm, ctx(running=set(), seen=seen, proc_tasks=lambda: {"b1234567"}))[0]
        == A.ARMED
    )
    # Gone from both: fired.
    assert A.evaluate(arm, ctx(running=set(), seen=seen, proc_tasks=set))[0] == A.FIRED
    # Control: never seen running after the arm, absence proves nothing.
    assert A.evaluate(arm, ctx(running=set(), seen={}, proc_tasks=set))[0] == A.ARMED


def test_note_running_ignores_a_stop_before_the_arm_stamp():
    arm = arm_of(["EXIT:b1234567"], at_min=10)
    seen = A.note_running({}, [({}, arm)], {"b1234567"}, T0 + datetime.timedelta(minutes=5))
    assert seen == {"0123abcd": []}


def test_exit_at_arm_time_must_be_listed_running():
    assert A.parse_when(["EXIT:b1234567"], world(running={"b1234567"})) == ["EXIT:b1234567"]
    with pytest.raises(A.TokenError, match="not listed running"):
        A.parse_when(["EXIT:b1234567"], world(running={"other999"}))
    with pytest.raises(A.TokenError, match="unreadable"):
        A.parse_when(["EXIT:b1234567"], world(running=None, running_why="no file"))


def _receipt(tmp_path, **doc):
    path = tmp_path / "prepush-receipt.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return lambda: A.read_json(path)


def test_ci_quick_done_fires_on_a_whole_receipt_finished_after_the_arm_whatever_its_exit(tmp_path):
    arm = arm_of(["CI-QUICK:done"], at_min=10)
    older = _receipt(tmp_path, finishedAt="%s.000Z" % at(5)[:-1], whole=True, exitCode=0)
    assert A.evaluate(arm, ctx(ci_latest=older))[0] == A.ARMED
    newer_red = _receipt(tmp_path, finishedAt="%s.804Z" % at(20)[:-1], whole=True, exitCode=1)
    verdict, why = A.evaluate(arm, ctx(ci_latest=newer_red))
    assert verdict == A.FIRED
    assert "exitCode=1" in why
    partial = _receipt(tmp_path, finishedAt="%s.000Z" % at(20)[:-1], whole=False, exitCode=0)
    assert A.evaluate(arm, ctx(ci_latest=partial))[0] == A.ARMED
    no_code = _receipt(tmp_path, finishedAt="%s.000Z" % at(20)[:-1], whole=True, exitCode=False)
    assert A.evaluate(arm, ctx(ci_latest=no_code))[0] == A.ARMED


def test_ci_quick_done_names_an_unreadable_receipt(tmp_path):
    bad = tmp_path / "prepush-receipt.json"
    bad.write_text("{not json", encoding="utf-8")
    verdict, why = A.evaluate(arm_of(["CI-QUICK:done"]), ctx(ci_latest=lambda: A.read_json(bad)))
    assert verdict == A.ARMED
    assert "unreadable" in why
    gone = tmp_path / "absent.json"
    assert (
        "absent"
        in A.evaluate(arm_of(["CI-QUICK:done"]), ctx(ci_latest=lambda: A.read_json(gone)))[1]
    )


def test_vm_check_done_fires_on_a_receipt_finished_after_the_arm():
    arm = arm_of(["VM-CHECK:done"], at_min=10)
    older = {"finishedAt": at(5), "status": "VERIFIED"}
    assert A.evaluate(arm, ctx(vm_latest=lambda: (older, "")))[0] == A.ARMED
    newer = {"finishedAt": at(20), "status": "FAILED"}
    assert A.evaluate(arm, ctx(vm_latest=lambda: (newer, "")))[0] == A.FIRED
    verdict, why = A.evaluate(
        arm, ctx(vm_latest=lambda: (None, "receipt.json fails vm_tier.validate (x)"))
    )
    assert verdict == A.ARMED
    assert "validate" in why


def test_vm_latest_names_a_receipt_that_fails_the_schema(tmp_path):
    folder = tmp_path / ".ci" / "cache" / "vm-check"
    folder.mkdir(parents=True)
    (folder / "receipt.json").write_text(json.dumps({"finishedAt": at(20)}), encoding="utf-8")
    doc, why = A.vm_latest(tmp_path)
    assert doc is None
    assert "vm_tier.validate" in why


def test_state_tokens_are_judged_live():
    arm = arm_of(["PUSHED:head", "BENCH:deployed"])
    assert A.evaluate(arm, ctx(pushed=lambda: True, bench=lambda: False))[0] == A.ARMED
    assert A.evaluate(arm, ctx(pushed=lambda: True, bench=lambda: True))[0] == A.FIRED
    v = arm_of(["VM-CHECK:verified", "CI-QUICK:verified"])
    assert (
        A.evaluate(v, ctx(vm_verified=lambda: True, ci_green=lambda: (False, "red")))[0] == A.ARMED
    )
    assert (
        A.evaluate(v, ctx(vm_verified=lambda: True, ci_green=lambda: (True, "green")))[0] == A.FIRED
    )


def test_needs_sugar_resolves_and_none_is_refused():
    assert A.parse_when(["NEEDS:verified-vmcheck", "NEEDS:pushed-head"], world()) == [
        "VM-CHECK:verified",
        "PUSHED:head",
    ]
    with pytest.raises(A.TokenError, match="waits on nothing"):
        A.parse_when(["NEEDS:none"], world())
    with pytest.raises(A.TokenError, match="not one of"):
        A.parse_when(["CI-QUICK:green"], world())


def test_defer_closed_fires_after_the_window_and_voids_when_answered():
    # The window is read from the wall clock (wl_core.stamp_age_min), so the stamps are real ones.
    now = C.utcnow()
    old_upd = A.stamp(now - datetime.timedelta(minutes=200))
    rec = {"id": "d0d0d0d0", "state": "?", "line": "- [?] pick DEFAULT: land it", "upd": old_upd}
    arm = arm_of(["DEFER-CLOSED:#d0d0d0d0"], exp_h=24 * 365)
    real = A.Ctx(root=pathlib.Path("/x"), now=now, by_id={"d0d0d0d0": rec})
    assert A.evaluate(arm, real)[0] == A.FIRED
    fresh = dict(rec, upd=C.stamp_now())
    assert (
        A.evaluate(arm, A.Ctx(root=pathlib.Path("/x"), now=now, by_id={"d0d0d0d0": fresh}))[0]
        == A.ARMED
    )
    answered = dict(rec, state=" ")
    assert (
        A.evaluate(arm, A.Ctx(root=pathlib.Path("/x"), now=now, by_id={"d0d0d0d0": answered}))[0]
        == A.VOID
    )


def test_defer_closed_at_arm_time_needs_a_deferral_with_a_default():
    by_id = {
        "d0d0d0d0": {"id": "d0d0d0d0", "state": "?", "line": "- [?] x DEFAULT: y"},
        "e0e0e0e0": {"id": "e0e0e0e0", "state": " ", "line": "- [ ] x"},
        "f0f0f0f0": {"id": "f0f0f0f0", "state": "?", "line": "- [?] no default"},
    }
    assert A.parse_when(["DEFER-CLOSED:#d0d0d0d0"], world(by_id=by_id)) == [
        "DEFER-CLOSED:#d0d0d0d0"
    ]
    with pytest.raises(A.TokenError, match="not a \\[\\?\\]"):
        A.parse_when(["DEFER-CLOSED:#e0e0e0e0"], world(by_id=by_id))
    with pytest.raises(A.TokenError, match="no DEFAULT"):
        A.parse_when(["DEFER-CLOSED:#f0f0f0f0"], world(by_id=by_id))


def test_ticked_fires_on_x_and_voids_on_a_tombstone():
    arm = arm_of(["TICKED:#b0b0b0b0"])
    assert A.evaluate(arm, ctx(by_id={"b0b0b0b0": {"state": " "}}))[0] == A.ARMED
    assert A.evaluate(arm, ctx(by_id={"b0b0b0b0": {"state": "x"}}))[0] == A.FIRED
    assert A.evaluate(arm, ctx(by_id={}))[0] == A.VOID
    with pytest.raises(A.TokenError, match="names no item"):
        A.parse_when(["TICKED:#b0b0b0b0"], world())
    with pytest.raises(A.TokenError, match="already ticked"):
        A.parse_when(
            ["TICKED:#b0b0b0b0"], world(by_id={"b0b0b0b0": {"id": "b0b0b0b0", "state": "x"}})
        )


# ---------------------------------------------------------------------------- BOX: committed ticks only

PLAN = """# PLAN: widgets
Status: approved

## Boxes

- [%s] B1 [writer] build the first widget carefully
- [ ] B2 [writer] build the second widget carefully
"""
B1_SIG = "e1d00ffe"


def git(repo, *args):
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture
def plan_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "agent" / "plans").mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "agent" / "plans" / "PLAN-w.md").write_text(PLAN % " ", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "plan")
    return repo


def box_ctx(repo):
    return A.Ctx(root=repo, now=C.utcnow(), by_id={}, show_head=lambda p: A.show_head(repo, p))


def test_box_fires_only_on_a_committed_tick(plan_repo):
    token = "BOX:agent/plans/PLAN-w.md#%s" % B1_SIG
    w = A.ArmWorld(root=plan_repo, now=C.utcnow(), by_id={})
    assert A.parse_when([token], w) == [token]
    arm = arm_of([token])
    assert A.evaluate(arm, box_ctx(plan_repo))[0] == A.ARMED
    # An uncommitted [x] in the working tree does not fire.
    (plan_repo / "agent" / "plans" / "PLAN-w.md").write_text(PLAN % "x", encoding="utf-8")
    assert A.evaluate(arm, box_ctx(plan_repo))[0] == A.ARMED
    git(plan_repo, "commit", "-qam", "tick")
    verdict, why = A.evaluate(arm, box_ctx(plan_repo))
    assert verdict == A.FIRED
    assert "ticked in HEAD" in why


def test_box_voids_when_the_sig_leaves_heads_plan_and_refuses_a_done_box(plan_repo):
    arm = arm_of(["BOX:agent/plans/PLAN-w.md#%s" % B1_SIG])
    (plan_repo / "agent" / "plans" / "PLAN-w.md").write_text(
        PLAN.replace("first widget carefully", "first gadget instead") % " ", encoding="utf-8"
    )
    git(plan_repo, "commit", "-qam", "rewrite")
    assert A.evaluate(arm, box_ctx(plan_repo))[0] == A.VOID
    with pytest.raises(A.TokenError, match="absent"):
        A.parse_when(
            ["BOX:agent/plans/PLAN-w.md#%s" % B1_SIG],
            A.ArmWorld(root=plan_repo, now=C.utcnow(), by_id={}),
        )
    with pytest.raises(A.TokenError, match="not in the commit"):
        A.parse_when(
            ["BOX:agent/plans/PLAN-x.md#%s" % B1_SIG],
            A.ArmWorld(root=plan_repo, now=C.utcnow(), by_id={}),
        )


# ---------------------------------------------------------------------------- evaluate: AND, expiry, latch


def test_tokens_combine_with_and_and_void_wins():
    arm = arm_of(["TICKED:#b0b0b0b0", "PUSHED:head"])
    assert (
        A.evaluate(arm, ctx(by_id={"b0b0b0b0": {"state": "x"}}, pushed=lambda: False))[0] == A.ARMED
    )
    assert (
        A.evaluate(arm, ctx(by_id={"b0b0b0b0": {"state": "x"}}, pushed=lambda: True))[0] == A.FIRED
    )
    assert A.evaluate(arm, ctx(by_id={}, pushed=lambda: True))[0] == A.VOID


def test_an_unfired_arm_expires_and_a_latched_one_answers_its_latch():
    arm = arm_of(["PUSHED:head"], exp_h=1)
    assert A.evaluate(arm, ctx(now_min=59))[0] == A.ARMED
    assert A.evaluate(arm, ctx(now_min=60))[0] == A.EXPIRED
    latched = dict(arm, verdict=A.FIRED, why="earlier evidence")
    assert A.evaluate(latched, ctx(now_min=600)) == (A.FIRED, "earlier evidence")


def test_default_expiry_follows_the_latest_not_before():
    nb = T0 + datetime.timedelta(days=3)
    assert A.default_expiry(T0, ["NOT-BEFORE:%s" % A.stamp(nb)]) == nb + datetime.timedelta(
        hours=24
    )
    assert A.default_expiry(T0, ["PUSHED:head"]) == T0 + datetime.timedelta(hours=24)


def test_covers_is_bounded_by_expiry_and_by_the_block_after_a_fire():
    arm = arm_of(["PUSHED:head"], exp_h=1)
    assert A.covers(arm, T0 + datetime.timedelta(minutes=30), armed_blocks=False)
    assert not A.covers(arm, T0 + datetime.timedelta(minutes=61), armed_blocks=True)
    fired = dict(arm, verdict=A.FIRED)
    assert A.covers(fired, T0, armed_blocks=True)
    assert not A.covers(fired, T0, armed_blocks=False)
    assert not A.covers(dict(arm, verdict=A.EXPIRED), T0, armed_blocks=True)
    assert not A.covers(dict(arm, verdict=A.VOID), T0, armed_blocks=True)
    assert not A.covers(dict(fired, started_at=at(1)), T0, armed_blocks=True)
    assert not A.covers(None, T0, armed_blocks=True)


def test_live_arm_is_inert_on_a_done_item():
    arm = arm_of(["PUSHED:head"])
    assert A.live_arm({"state": " ", "arm": arm}) is arm
    assert A.live_arm({"state": "x", "arm": arm}) is None
    assert A.live_arm({"state": " ", "arm": dict(arm, started_at=at(1))}) is None


# ---------------------------------------------------------------------------- the store: fold, latch, compaction


@pytest.fixture
def store(tmp_path, monkeypatch):
    d = tmp_path / "store"
    d.mkdir()
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("WORKLIST_STORE_DIR", str(d))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("WORKLIST_READ_MEMO", "off")
    monkeypatch.setenv("WORKLIST_SESSION_ID", ME + "-1111-2222-3333-444444444444")
    return types.SimpleNamespace(d=d, root=proj, wl=tmp_path / "WORKLIST.md", tmp=tmp_path)


def armed_store(s):
    rid = S.add_item(s.wl, ME, "held landing (%s)" % ME, root=s.root)
    aid = S.arm_item(
        s.wl, ME, rid, ["PUSHED:head"], cmd="./run.sh worktree land x", exp=at(60 * 24)
    )
    return rid, aid


def fold_arm(s, rid):
    return S.load(s.wl, sync=False).by_id[rid].get("arm")


def test_arm_event_folds_to_the_design_shape(store):
    rid, aid = armed_store(store)
    arm = fold_arm(store, rid)
    assert arm["aid"] == aid
    assert arm["when"] == ["PUSHED:head"]
    assert arm["verdict"] == ""
    assert arm["cmd"] == "./run.sh worktree land x"
    lines = [json.loads(x) for f in store.d.glob("*.jsonl") for x in f.read_text().splitlines()]
    ev = next(e for e in lines if e["ev"] == "arm")
    assert set(ev) >= {"ev", "id", "at", "by", "aid", "when", "run", "cmd", "sha", "lease", "exp"}


def test_a_duplicate_armfire_is_a_no_op_and_a_stale_aid_start_is_ignored(store):
    rid, aid = armed_store(store)
    S.armfire_item(store.wl, ME, rid, aid, "fired", "first evidence")
    S.armfire_item(store.wl, ME, rid, aid, "void", "second evidence")
    arm = fold_arm(store, rid)
    assert arm["verdict"] == "fired"
    assert arm["why"] == "first evidence"
    S.armstart_item(store.wl, ME, rid, "ffffffff")
    assert fold_arm(store, rid)["started_at"] == ""
    S.armstart_item(store.wl, ME, rid, aid)
    assert fold_arm(store, rid)["started_at"]


def test_a_stale_aid_armfire_and_disarm_are_ignored_after_a_rearm(store):
    rid, aid = armed_store(store)
    S.disarm_item(store.wl, ME, rid, aid, "replanned")
    assert fold_arm(store, rid) is None
    aid2 = S.arm_item(store.wl, ME, rid, ["BENCH:deployed"], cmd="echo go", exp=at(60))
    assert aid2 != aid
    S.armfire_item(store.wl, ME, rid, aid, "fired", "old generation")
    S.disarm_item(store.wl, ME, rid, aid, "old generation")
    arm = fold_arm(store, rid)
    assert arm["aid"] == aid2
    assert arm["verdict"] == ""


def test_an_armfire_with_an_unknown_verdict_is_refused_at_the_writer(store):
    rid, aid = armed_store(store)
    with pytest.raises(ValueError, match="not fired, expired or void"):
        S.armfire_item(store.wl, ME, rid, aid, "maybe", "x")


def test_an_arm_survives_compaction_with_its_aid_and_latch(store, capsys):
    rid, aid = armed_store(store)
    S.armfire_item(store.wl, ME, rid, aid, "fired", "PUSHED:head: HEAD is on its upstream")
    before = fold_arm(store, rid)
    S.compact_store(store.wl, root=store.root, me=ME, projects_dir=store.tmp / "none")
    capsys.readouterr()
    after = fold_arm(store, rid)
    assert after is not None, "the arm was lost at compaction"
    assert after["aid"] == aid
    assert after["verdict"] == "fired"
    assert after["why"] == before["why"]
    assert {
        e.get("ev")
        for f in store.d.glob("*.jsonl")
        for e in map(json.loads, f.read_text().splitlines())
    } == {"add"}


def test_control_without_the_am_carry_compaction_drops_the_arm(store):
    rid, aid = armed_store(store)
    payload = S.snapshot_events(S.load(store.wl, sync=False))
    carried = [e for e in payload if e.get("am")]
    assert carried
    assert carried[0]["am"]["aid"] == aid
    for e in payload:
        e.pop("am", None)
    records = S._fold_events(payload)[0]
    assert "arm" not in records[rid]


def test_a_started_arm_is_not_carried_by_compaction(store):
    rid, aid = armed_store(store)
    S.armfire_item(store.wl, ME, rid, aid, "fired", "x")
    S.armstart_item(store.wl, ME, rid, aid)
    payload = S.snapshot_events(S.load(store.wl, sync=False))
    assert not [e for e in payload if e.get("am")]


def test_sweep_latches_once_and_returns_the_due_arm(store):
    rid, _aid = armed_store(store)
    fold = S.load(store.wl, sync=False)
    c = A.Ctx(root=store.root, now=C.utcnow(), by_id=fold.by_id, pushed=lambda: True)
    rows = A.sweep(store.wl, ME, fold.items, ME, c)
    assert [(r["id"], v) for r, _a, v, _w in rows] == [(rid, A.FIRED)]
    fold = S.load(store.wl, sync=False)
    assert fold.by_id[rid]["arm"]["verdict"] == A.FIRED
    # A second sweep appends no second latch.
    n = sum(len(f.read_text().splitlines()) for f in store.d.glob("*.jsonl"))
    rows = A.sweep(store.wl, ME, fold.items, ME, c)
    assert len(rows) == 1
    assert sum(len(f.read_text().splitlines()) for f in store.d.glob("*.jsonl")) == n


def test_sweep_control_an_unfired_arm_writes_nothing(store):
    rid, _aid = armed_store(store)
    fold = S.load(store.wl, sync=False)
    c = A.Ctx(root=store.root, now=C.utcnow(), by_id=fold.by_id, pushed=lambda: False)
    assert A.sweep(store.wl, ME, fold.items, ME, c) == []
    assert fold_arm(store, rid)["verdict"] == ""


# ---------------------------------------------------------------------------- STATE.md `## Armed`

BODY = (
    "x" * 260
    + "\n\n## Next action\nLand the rotation fix.\n\n## Big pieces\nnone: no plan carries an open box.\n"
)


def test_unarmed_while_an_arm_is_live_and_ok_with_none():
    assert S.agent_state_shape(BODY)[0] == "ok"
    assert S.agent_state_shape(BODY, None, [])[0] == "ok"
    verdict, detail = S.agent_state_shape(BODY, None, ["abcdef12"])
    assert verdict == "unarmed"
    assert "#abcdef12" in detail
    named = BODY + "\n## Armed\n- #abcdef12 lands the renet lease after CI-QUICK:done\n"
    assert S.agent_state_shape(named, None, ["abcdef12"])[0] == "ok"
    partial = BODY + "\n## Armed\n- #abcdef12 one\n"
    verdict, detail = S.agent_state_shape(partial, None, ["abcdef12", "99887766"])
    assert verdict == "unarmed"
    assert "#99887766" in detail


def test_agent_state_state_reads_the_arms_from_the_fold(store):
    rid, _aid = armed_store(store)
    sdir = store.root / "agent" / ME
    sdir.mkdir(parents=True)
    (sdir / "STATE.md").write_text(
        "## SESSION %s %s\n%s" % (ME, C.stamp_now(), BODY), encoding="utf-8"
    )
    fold = S.load(store.wl, sync=False)
    assert S.agent_state_state(store.root, ME, fold=fold)[0] == "unarmed"
    assert S.agent_state_state(store.root, ME)[0] == "ok"
    (sdir / "STATE.md").write_text(
        "## SESSION %s %s\n%s\n## Armed\n- #%s held landing\n" % (ME, C.stamp_now(), BODY, rid),
        encoding="utf-8",
    )
    assert S.agent_state_state(store.root, ME, fold=fold)[0] == "ok"
