"""Lease continuity without hand bookkeeping: worker:lead, auto-lease, --relay and id lists, BLOCKED_BY (agent/plans/PLAN-stop-hook-continuity.md P2.1-P2.4).

Every case drives the real CLI and the real Stop hook through `wlfix`, and every FIRE has an inverse that differs by one planted fact.
"""

from __future__ import annotations

import json
import re

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import (
    W1,
    linked,
    mk_sub,
    plant_lease,
    plant_queued,
    private_stop,
    stamp,
    subagents_dir,
    until,
    write_plan,
)
from rediacc_hooks.tests.wlfix import wl  # noqa: F401


def add(fix, text: str) -> str:
    got = fix.cli("--add", wlfix.ME, text)
    assert got.rc == 0, got.err[:300]
    found = re.search(r"added #([0-9a-f]+)", got.out)
    assert found, got.out[:200]
    return found.group(1)


def shell(ident: str) -> dict:
    return {"id": ident, "type": "shell", "status": "running", "description": "a watch"}


def ready(fix) -> None:
    fix.brief_now()
    fix.hand_now()


# ---- P2.1 worker:lead ---------------------------------------------------------


def test_l1_a_lead_lease_survives_a_shell_replacement_without_a_new_lease(wl):  # noqa: F811
    """CONTROL: before P2.1 `--lease ... worker:lead` was accepted as any other name and, with no task of that id, failed closed on the first stop after its expiry; a shell replacement needed a new `--lease` every time."""
    ready(wl)
    wl.say("starting")
    wl.run()  # writes the event sidecar a lease is checked against
    item = add(wl, "(deadbeef) driven inline by the lead")
    got = wl.cli("--lease", wlfix.ME, item, "+30", "worker:lead", "driving it")
    assert got.rc == 0, got.err[:300]
    assert "WARNING" not in got.out, "worker:lead is not a task id to verify: %s" % got.out
    said = "working\n\n## Remaining\n- #%s in flight, inline" % item
    for sid in ("bshell01", "bshell02"):
        wl.bg = json.dumps([shell(sid)])
        wl.newturn()
        wl.say(said)
        out = wl.run().out
        assert "worker:lead with nothing of this session running" not in out, out[:600]
        assert "OPEN worklist item" not in out, out[:600]


def test_l1b_inverse_a_lead_lease_with_nothing_running_is_open(wl):  # noqa: F811
    ready(wl)
    item = add(wl, "(deadbeef) driven inline by the lead")
    wl.cli("--lease", wlfix.ME, item, "+30", "worker:lead", "driving it")
    wl.say("working\n\n## Remaining\n- #%s in flight, inline" % item)
    out = wl.run({"WORKLIST_FOCUS": "off"}).out
    assert "worker:lead with nothing of this session running" in out, out[:800]


def test_l1c_the_lead_holds_at_most_three(wl):  # noqa: F811
    items = [add(wl, "(deadbeef) inline %d" % i) for i in range(4)]
    for item in items[:3]:
        assert wl.cli("--lease", wlfix.ME, item, "+30", "worker:lead").rc == 0
    got = wl.cli("--lease", wlfix.ME, items[3], "+30", "worker:lead")
    assert got.rc != 0, got.out
    assert "the cap is 3" in got.err, got.err[:300]


def test_l1d_a_covered_lead_lease_is_renewed_by_the_hook(wl):  # noqa: F811
    ready(wl)
    item = add(wl, "(deadbeef) driven inline by the lead")
    wl.cli("--lease", wlfix.ME, item, "+10", "worker:lead")
    wl.bg = json.dumps([shell("bshell01")])
    wl.say("working\n\n## Remaining\n- #%s in flight, inline" % item)
    wl.run()
    leases = [
        json.loads(ln)
        for ln in wl.wl_events().splitlines()
        if '"ev": "lease"' in ln or '"ev":"lease"' in ln
    ]
    assert len(leases) == 2, leases
    assert leases[-1]["until"] > leases[0]["until"], leases


# ---- P2.2 auto-lease from #id ----------------------------------------------------


def agent_naming(fix, aid: str, item: str) -> None:
    """A live agent whose first prompt names `#item`."""
    mk_sub(fix, aid, "general-purpose", 0)
    tx = subagents_dir(fix) / ("agent-%s.jsonl" % aid)
    lines = tx.read_text(encoding="utf-8").splitlines(keepends=True)
    first = {"type": "user", "message": {"content": "Your item is #%s. Do it." % item}}
    tx.write_text(json.dumps(first) + "\n" + "".join(lines[1:]), encoding="utf-8")


def test_l2_a_new_agent_whose_prompt_names_an_open_item_holds_its_lease(wl):  # noqa: F811
    """CONTROL: before P2.2 the item stayed open, and the roster reported an unleased writer, until the lead typed `--lease`."""
    ready(wl)
    item = add(wl, "(deadbeef) work handed to an agent")
    agent_naming(wl, "a7000000000000001", item)
    wl.say("delegated\n\n## Remaining\n- #%s with the agent" % item)
    out = wl.run().out
    assert "UNLEASED WRITER" not in out, out[:800]
    events = wl.wl_events()
    assert '"worker": "a7000000000000001"' in events or '"worker":"a7000000000000001"' in events, (
        events[-800:]
    )


def test_l2b_inverse_a_peers_item_is_never_auto_leased(wl):  # noqa: F811
    ready(wl)
    peer = wl.cli_as("cafe1234", "--add", "cafe1234", "(cafe1234) the peer's own work")
    found = re.search(r"added #([0-9a-f]+)", peer.out)
    assert found, peer.out[:200]
    item = found.group(1)
    agent_naming(wl, "a7000000000000001", item)
    wl.say("delegated\n\n## Remaining\n- nothing of mine")
    wl.run()
    assert '"a7000000000000001"' not in wl.wl_events(), wl.wl_events()[-600:]


# ---- P2.3 id lists and --relay -----------------------------------------------------


def test_l3_relay_moves_three_leases_in_one_call(wl):  # noqa: F811
    """CONTROL: before P2.3 a replaced shell needed one `--lease` per item it had held."""
    items = [add(wl, "(deadbeef) watched %d" % i) for i in range(3)]
    got = wl.cli("--lease", wlfix.ME, ",".join(items), "+30", "worker:bold01")
    assert got.rc == 0, got.err[:300]
    assert got.out.count("leased #") == 3, got.out
    got = wl.cli("--relay", wlfix.ME, "bold01", "worker:bnew02")
    assert got.rc == 0, got.err[:300]
    assert "relayed 3 lease(s) from worker:bold01 to worker:bnew02" in got.out, got.out
    listed = wl.cli("--list").out
    assert listed.count("worker:bnew02") == 3, listed


def test_l3b_inverse_relay_from_a_worker_holding_nothing_is_refused(wl):  # noqa: F811
    got = wl.cli("--relay", wlfix.ME, "nobody1", "bnew02")
    assert got.rc != 0, got.out
    assert "nothing relayed" in got.err, got.err


# ---- P2.4 BLOCKED_BY ---------------------------------------------------------------


def test_l4_a_blocked_item_waits_and_reopens_when_its_blocker_closes(wl):  # noqa: F811
    """CONTROL: before P2.4 the blocked item was ordinary open work, so `open-items` listed both."""
    ready(wl)
    root = add(wl, "(deadbeef) the root of the chain")
    child = add(wl, "(deadbeef) waits on the root BLOCKED_BY:#%s" % root)
    wl.say("working\n\n## Remaining\n- #%s and #%s" % (root, child))
    reason = json.loads(wl.run({"WORKLIST_FOCUS": "off"}).out)["reason"]
    open_block = reason.split("OPEN worklist item(s)", 1)[1].split("\n\n", 1)[0]
    assert "1 OPEN worklist item(s)" in reason, reason[:800]
    assert "the root of the chain" in open_block, open_block
    assert "waits on the root" not in open_block, open_block
    assert "#%s waiting (#%s)" % (child, root) in reason, reason[-800:]
    assert wl.cli("--tick", wlfix.ME, root, "done, exit code 0").rc == 0
    wl.newturn()
    wl.say("working\n\n## Remaining\n- #%s" % child)
    out = wl.run({"WORKLIST_FOCUS": "off"}).out
    assert "1 OPEN worklist item(s)" in out, out[:800]
    assert "waits on the root" in out, out[:800]
    doc = json.loads(wl.stem(".state-deadbeef.json").read_text(encoding="utf-8"))
    texts = [e.get("text", "") for e in doc.get("outq", {}).get("items", [])]
    assert (
        any(t.startswith("UNBLOCKED #%s" % child) for t in texts) or "UNBLOCKED #%s" % child in out
    ), (
        texts,
        out[-600:],
    )


def test_l4b_inverse_an_unknown_blocker_and_a_cycle_are_refused(wl):  # noqa: F811
    got = wl.cli("--add", wlfix.ME, "(deadbeef) waits on nothing BLOCKED_BY:#abcdef12")
    assert got.rc == 2, (got.rc, got.err)
    a = add(wl, "(deadbeef) first")
    b = add(wl, "(deadbeef) second BLOCKED_BY:#%s" % a)
    got = wl.cli("--update", wlfix.ME, a, "now waits on the second BLOCKED_BY:#%s" % b)
    assert got.rc == 2, (got.rc, got.err)
    assert "cycle" in got.err, got.err


def test_l4c_a_blocked_by_set_by_update_makes_the_item_wait(wl):  # noqa: F811
    """2026-09-25: `--update <id> 'BLOCKED_BY:#<root>'` passed validation, then the fold kept it only as the display note, so `waiting_on` never saw it and the item stayed open work. A later update without the token must not unblock it either."""
    ready(wl)
    root = add(wl, "(deadbeef) the root of the chain")
    child = add(wl, "(deadbeef) an ordinary item")
    assert wl.cli("--update", wlfix.ME, child, "BLOCKED_BY:#%s waits on the root" % root).rc == 0
    assert wl.cli("--update", wlfix.ME, child, "progress note with no token").rc == 0
    wl.say("working\n\n## Remaining\n- #%s and #%s" % (root, child))
    reason = json.loads(wl.run({"WORKLIST_FOCUS": "off"}).out)["reason"]
    open_block = reason.split("OPEN worklist item(s)", 1)[1].split("\n\n", 1)[0]
    assert "1 OPEN worklist item(s)" in reason, reason[:800]
    assert "an ordinary item" not in open_block, open_block
    assert "#%s waiting (#%s)" % (child, root) in reason, reason[-800:]


def test_l5_a_lease_names_exactly_one_worker(wl):  # noqa: F811
    """2026-09-25: `worker:a1,a2` was accepted and stored whole; the roster matches one id, so both writers read as UNLEASED."""
    ready(wl)
    item = add(wl, "(deadbeef) two writers on one item")
    got = wl.cli("--lease", wlfix.ME, item, "+60", "worker:abc123def,fed321cba", "note")
    assert got.rc != 0, (got.rc, got.out)
    assert "not one worker id" in got.err, got.err
    assert wl.cli("--lease", wlfix.ME, item, "+60", "worker:abc123def", "note").rc == 0


def test_l6_the_operator_switch_turns_the_stop_path_off_and_only_it(wl):  # noqa: F811
    """Operator order 2026-09-25: `.ci/config/stop-hook.json` `enabled: false` allows every stop; verbs keep working; a missing or unreadable file keeps the hook on."""
    ready(wl)
    add(wl, "(deadbeef) open work that would block")
    wl.say("working\\n\\n## Remaining\\n- the item")
    assert (
        "OPEN worklist item" in wl.run({"WORKLIST_FOCUS": "off"}).out
    )  # CONTROL: no config, the hook blocks
    cfg = wl.proj / ".ci" / "config" / "stop-hook.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("{not json", encoding="utf-8")
    wl.newturn()
    wl.say("working\\n\\n## Remaining\\n- the item")
    assert "OPEN worklist item" in wl.run({"WORKLIST_FOCUS": "off"}).out  # unreadable -> still on
    cfg.write_text('{"enabled": false}', encoding="utf-8")
    wl.newturn()
    wl.say("working\\n\\n## Remaining\\n- the item")
    assert wl.run({"WORKLIST_FOCUS": "off"}).out.strip() == ""
    assert wl.cli("--list", "--open", wlfix.ME).rc == 0  # verbs unaffected


# ---- R20260925.5: an expired queue lease on a waiting item reads as waiting ---------------------------


def queued_waiter_world(fix, with_token: bool) -> None:
    """A blocker leased to a live writer, and a queued item whose queue lease expired: with `with_token` it declares BLOCKED_BY the blocker (the #bea10927 shape of 19:45:03 on 2026-09-24), without it it is an ordinary dead queue lease."""
    ready(fix)
    mk_sub(fix, W1, "general-purpose", 1)
    plant_lease(fix, "b10c0001", W1)
    text = "(deadbeef) golden update waits on the writer"
    plant_queued(
        fix, "q0000old", text + (" BLOCKED_BY:#b10c0001" if with_token else ""), 30, expired=True
    )
    fix.say("working\n\n## Remaining\n- #b10c0001 on the writer, #q0000old queued")


def test_l7_an_expired_queue_lease_waiting_on_an_open_blocker_does_not_fail_closed(wl):  # noqa: F811
    """CONTROL: before R20260925.5 the expired lease failed closed into an open item although its blocker was still being worked, and the lead renewed it by hand with the note "blocked on A3"."""
    queued_waiter_world(wl, with_token=True)
    out = wl.run({"WORKLIST_FOCUS": "off"}).out
    assert "lease expired; finish it" not in out, out[:1200]
    # The guide says the same: waiting, not a dead lease to re-lease.
    assert "#q0000old LEASE DEAD" not in out, out[:1600]
    assert "[>] #q0000old waiting (#b10c0001)" in out, out[:1600]


def test_l7b_inverse_the_same_lease_without_the_token_fails_closed_and_names_the_remedy(wl):  # noqa: F811
    queued_waiter_world(wl, with_token=False)
    out = wl.run({"WORKLIST_FOCUS": "off"}).out
    assert "lease expired; finish it" in out, out[:1200]
    assert "#q0000old LEASE DEAD" in out, out[:1600]
    assert "--update deadbeef q0000old 'BLOCKED_BY:#<blocker>'" in out, out[:1600]


def test_l7c_the_queue_slot_block_names_blocked_by_as_the_remedy(wl):  # noqa: F811
    """V_QUEUE_SLOT: a free slot and a startable queued item; the block says how to mark one that is really waiting."""
    ready(wl)
    mk_sub(wl, W1, "general-purpose", 1)
    plant_lease(wl, "b10c0001", W1)
    plant_queued(wl, "q0000new", "(deadbeef) independent writer work", 10)
    wl.say("working\n\n## Remaining\n- #b10c0001 on the writer, #q0000new queued")
    out = wl.run({"WORKLIST_FOCUS": "off"}).out
    assert "QUEUED WORK AND A FREE WRITER SLOT" in out, out[:1200]
    assert "start #q0000new" in out, out[:1200]
    assert "--update deadbeef <id> 'BLOCKED_BY:#<blocker>'" in out, out[:1600]


# ---- agent/plans/PLAN-plan-priority-concurrency.md section 5b (T9): a queue lease beside a free slot, for an item a live plan holds ----


def held_world(fix) -> tuple[str, str]:
    """A PEER's fresh lease on an item of EXCLUSIVE plan E (the cross-session holder), and two open items of this session: one on plan F, which E's mutex holds, and one on E itself, which it does not. No writer of this session is live, so every slot is free."""
    ready(fix)
    e = write_plan(fix, "e", conc="exclusive -- regenerates every golden file")
    f = write_plan(fix, "f")
    plant_lease(
        fix, "e3000009", "a5555555555555555", owner="cafe1234", text=linked(e, "peer", "cafe1234")
    )
    return add(fix, linked(f, "held work")), add(fix, linked(e, "free work"))


def test_l8_a_queue_lease_beside_a_free_slot_is_accepted_for_a_held_item(wl):  # noqa: F811
    held, _free = held_world(wl)
    got = wl.cli("--lease", wlfix.ME, held, "+60", "worker:queue", "waiting on E")
    assert got.rc == 0, got.err[:600]
    assert "queued beside a free writer slot: PLAN-e.md is exclusive" in got.err, got.err[:600]
    notes = [
        json.loads(line).get("note", "")
        for line in wl.wl_events().splitlines()
        if line.strip()
        and json.loads(line).get("ev") == "lease"
        and json.loads(line).get("id") == held
    ]
    assert notes, "no lease event for #%s" % held
    assert notes[-1] == "waiting on E HELD_BY:PLAN-e.md", notes


def test_l8b_inverse_an_unheld_item_is_still_refused_with_a_free_slot(wl):  # noqa: F811
    _held, free = held_world(wl)
    got = wl.cli("--lease", wlfix.ME, free, "+60", "worker:queue")
    assert got.rc != 0, got.out[:300]
    assert "worker:queue is only for writer work the cap forbids starting" in got.err, got.err[:600]


def test_l8c_inverse_an_expired_peer_lease_holds_nothing(wl):  # noqa: F811
    """v2's control: only a FRESH lease makes a plan live."""
    ready(wl)
    e = write_plan(wl, "e", conc="exclusive -- regenerates every golden file")
    f = write_plan(wl, "f")
    with wl.events.open("a", encoding="utf-8") as fh:
        for ev in (
            {"ev": "add", "id": "e3000009", "at": stamp(300), "by": "cafe1234", "s": " ", "o": "cafe1234", "t": linked(e, "peer", "cafe1234")},
            {"ev": "lease", "id": "e3000009", "at": stamp(290), "by": "cafe1234", "until": until(-200), "worker": "a5555555555555555", "note": ""},
        ):  # fmt: skip
            fh.write(json.dumps(ev) + "\n")
    held = add(wl, linked(f, "held work"))
    got = wl.cli("--lease", wlfix.ME, held, "+60", "worker:queue")
    assert got.rc != 0, got.out[:300]
    assert "worker:queue is only for writer work" in got.err, got.err[:600]


def test_l8m_without_the_held_branch_l8_is_refused_again(wl):  # noqa: F811
    held, _free = held_world(wl)
    stop = private_stop(wl, "worklist.py", "                and not _held_by\n", "")
    wl.hook = stop / "worklist.py"
    got = wl.cli("--lease", wlfix.ME, held, "+60", "worker:queue")
    assert got.rc != 0, "l8m: l8 does not depend on the held branch: %s" % got.err[:400]
