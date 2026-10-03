"""The live PR's item scope inside `classify_items` and the guide (agent/plans/PLAN-stop-hook-one-plan-scope.md, SC4, Design 2).

`classify_items(..., in_scope=pred)` sends a plain open item of this session that fails the predicate to a fifth return value, `queued`, instead of the open list, so every consumer of the open list is scoped by construction. A dead claim (a fail-closed lease, a `worker:lead` item with nothing live) is a loop duty and stays open whatever the predicate says. `in_scope=None` is today's behaviour.

The predicate here is built the way production builds it: the union of `wl_epic.plan_epics` over the PR's plan set, prerequisites included (ruling 7). The set itself comes from `wl_prscope.loop_state` (SC2); these cases plant it directly so they test the scoping, not the resolver.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import plant_item, stamp, write_plan
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

PROBE = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_core as C, wl_store as S, wl_epic as E, wl_checks as K
ev = json.loads(sys.stdin.read())
plans = json.loads(sys.argv[2])
start = C.project_start(ev)
root = C.project_root(start)
wl = C.worklist_for(start)
fold = S.load(wl, sync=True)
scope = set()
for rel in plans or []:
    scope |= E.plan_epics(rel)
pred = None if plans is None else (lambda rec: rec["id"] in scope)
got = S.classify_items(fold, ev["session_id"], in_scope=pred)
base = S.classify_items(S.load(wl, sync=True), ev["session_id"])
guide = K.guided_slice(S.load(wl, sync=True), ev["session_id"], me=ev["session_id"][:8], root=root, in_scope=pred)
print(json.dumps({
    "n": len(got),
    "open": got[0],
    "deferred": [r["id"] for r in got[2]],
    "in_flight": [r["id"] for r in got[3]],
    "queued": [r["id"] for r in got[4]],
    "base_open": base[0],
    "base_queued": [r["id"] for r in base[4]],
    "guide": guide,
}))
"""


def probe(fix, plans) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", PROBE, str(wlfix.STOP_DIR), json.dumps(plans)],
        input=fix.event(),
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, "the probe failed: %s" % proc.stderr[-1200:]
    return json.loads(proc.stdout)


def epic_for(fix, plan: str, *items: str) -> str:
    got = fix.cli("--epic", wlfix.ME, "new", "--plan", "agent/plans/%s" % plan, "epic of", plan)
    assert got.rc == 0, got.err[:300]
    found = re.search(r"epic #([0-9a-f]+)", got.out)
    assert found, got.out
    eid = found.group(1)
    if items:
        assert fix.cli("--epic", wlfix.ME, "add", eid, *items).rc == 0
    return eid


def plant_dead_lease(fix, item_id: str, worker: str) -> None:
    """An item whose lease expired two hours ago on a worker nothing runs."""
    past = stamp(120)[:16] + "Z"
    with fix.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "add",
                    "id": item_id,
                    "at": stamp(200),
                    "by": wlfix.ME,
                    "s": " ",
                    "o": wlfix.ME,
                    "t": "(deadbeef) dead lease %s" % item_id,
                }
            )
            + "\n"
        )
        fh.write(
            json.dumps(
                {
                    "ev": "lease",
                    "id": item_id,
                    "at": stamp(180),
                    "by": wlfix.ME,
                    "until": past,
                    "worker": worker,
                    "note": "",
                    "worker_verified": True,
                }
            )
            + "\n"
        )


def world(fix):
    """PR plan A, its prerequisite B, an unrelated plan C, and one item each plus one in no epic."""
    pr = write_plan(fix, "pr-own")
    pre = write_plan(fix, "pr-prereq")
    other = write_plan(fix, "unrelated")
    plant_item(fix, "aaaa0001", "(deadbeef) in the PR plan's epic")
    plant_item(fix, "bbbb0002", "(deadbeef) in the prerequisite's epic")
    plant_item(fix, "cccc0003", "(deadbeef) in an unrelated plan's epic")
    plant_item(fix, "dddd0004", "(deadbeef) in no epic at all")
    epic_for(fix, pr, "aaaa0001")
    epic_for(fix, pre, "bbbb0002")
    epic_for(fix, other, "cccc0003")
    return ["agent/plans/%s" % pr, "agent/plans/%s" % pre]


def joined(rows) -> str:
    return "\n".join(rows)


def test_classify_scope_pr_plan_and_prerequisite_items_stay_open(wl):  # noqa: F811
    got = probe(wl, world(wl))
    assert got["n"] == 5, "classify_items must return five values: %s" % got["n"]
    text = joined(got["open"])
    assert "in the PR plan's epic" in text, got
    assert "in the prerequisite's epic" in text, "ruling 7: a prerequisite's items block: %s" % got


def test_classify_scope_unrelated_and_epicless_items_are_queued(wl):  # noqa: F811
    got = probe(wl, world(wl))
    assert set(got["queued"]) == {"cccc0003", "dddd0004"}, got
    text = joined(got["open"])
    assert "unrelated plan's epic" not in text, got
    assert "no epic at all" not in text, got


def test_classify_scope_dead_lease_outside_the_epic_stays_open(wl):  # noqa: F811
    plans = world(wl)
    plant_dead_lease(wl, "eeee0005", "bdead0001")
    plant_dead_lease(wl, "ffff0006", "lead")
    got = probe(wl, plans)
    text = joined(got["open"])
    assert "eeee0005" in text, "a fail-closed lease is a loop duty, never queued: %s" % got
    assert "ffff0006" in text, "a worker:lead item with nothing live stays open: %s" % got
    assert "eeee0005" not in got["queued"], got
    assert "ffff0006" not in got["queued"], got


def test_classify_scope_deferred_items_are_never_queued(wl):  # noqa: F811
    plans = world(wl)
    defer = "q DEFAULT: do-it WHY: needs-an-operator-ruling HOW: operator-answers"
    assert wl.cli("--defer", wlfix.ME, "dddd0004", *defer.split()).rc == 0
    got = probe(wl, plans)
    assert "dddd0004" in got["deferred"], got
    assert "dddd0004" not in got["queued"], got


def test_classify_scope_none_equals_today(wl):  # noqa: F811
    """CONTROL: no predicate is today's result, every open item in `open_items` and nothing queued."""
    world(wl)
    got = probe(wl, None)
    assert got["open"] == got["base_open"], got
    assert got["queued"] == [], got
    assert got["base_queued"] == [], got
    assert len(got["open"]) == 4, got


def test_classify_scope_guide_lists_in_scope_items_only(wl):  # noqa: F811
    got = probe(wl, world(wl))
    guide = got["guide"]
    assert "#aaaa0001" in guide, guide
    assert "#bbbb0002" in guide, guide
    assert "#cccc0003" not in guide, guide
    assert "#dddd0004" not in guide, guide
    # CONTROL: with no predicate the guide lists all four.
    full = probe(wl, None)["guide"]
    for rid in ("aaaa0001", "bbbb0002", "cccc0003", "dddd0004"):
        assert "#%s" % rid in full, full


# ---- SC5 / SC6: the PR_LOOP profile through the real hook (Design 4 and 5) ------------------------------------
#
# A fixture checkout on the MMDD-N branch 1003-1 whose one PR read (wl_ci.pr_link) answers from the shared gh shim of test_wl_focus, so `wl_prscope.loop_state` resolves a real `live` state: the PR body's `Plan:` line names the PR plan, and QUEUE.md holds it and one queued plan. Every fire case has a control that differs by one planted fact; the mutation controls run a PRIVATE COPY of the hook with one line removed.

from rediacc_hooks.tests import test_wl_focus as F  # noqa: E402
from rediacc_hooks.tests.test_wl_cap_wait import mutated_hook  # noqa: E402

BRANCH = "1003-1"
PR_SCOPE = "One plan per PR: only this PR's plan, its prerequisites and the loop's duties block."
DEFER = "q DEFAULT: do-it WHY: needs-an-operator-ruling HOW: operator-answers"


def loop_plan(fix, name: str, opened: int = 1, done: int = 1, dep: str = "", owner: str = wlfix.ME):
    """agent/plans/PLAN-<name>.md with `done` ticked and `opened` open boxes; its rel path."""
    text = "# PLAN: %s fixture\n\nStatus: approved\nOwner: %s\nDepends-On: %s\n\n## Tasks\n\n" % (
        name,
        owner,
        dep or "no-dep -- a fixture plan that stands alone",
    )
    text += "".join("- [x] D%d the ticked %s fixture box\n" % (i, name) for i in range(done))
    text += "".join("- [ ] T%d the open %s fixture box\n" % (i, name) for i in range(opened))
    folder = fix.proj / "agent" / "plans"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ("PLAN-%s.md" % name)).write_text(text, encoding="utf-8")
    return "agent/plans/PLAN-%s.md" % name


def write_queue(fix, *rels: str) -> None:
    text = "# Plan queue\n\n## Promoted\n\n" + "".join(
        "%d. %s\n" % (i + 1, r) for i, r in enumerate(rels)
    )
    (fix.proj / "agent" / "plans" / "QUEUE.md").write_text(text, encoding="utf-8")


def pr_node(state: str, body: str, number: int = 543) -> dict:
    return {
        "number": number,
        "state": state,
        "body": body,
        "mergedAt": "2026-10-03T10:00:00Z" if state == "MERGED" else None,
        "closedAt": None if state == "OPEN" else "2026-10-03T10:00:00Z",
    }


def loop_world(fix, branch: str = BRANCH, red: bool = False, ci_ref: bool = False, opened: int = 1):
    """The live loop: PR #543 OPEN on `branch`, `Plan:` PLAN-pr-own.md, QUEUE.md holding it then PLAN-queued-next.md. Returns the PR plan's rel."""
    F.world(fix, ci=True, red=red)
    fix.git("switch", "-q", "-c", branch)
    if ci_ref:
        head = fix.git("rev-parse", "HEAD").stdout.strip()
        fix.git("update-ref", "refs/remotes/origin/%s" % branch, head)
    own = loop_plan(fix, "pr-own", opened=opened)
    nxt = loop_plan(fix, "queued-next", opened=2, done=0)
    write_queue(fix, own, nxt)
    F.merged_nodes(fix, [pr_node("OPEN", "Plan: %s\n\nsummary" % own)])
    return own


def run_stop(fix, extra: dict | None = None) -> wlfix.Result:
    return F.stop(fix, extra)


def keys_of(fix, got: wlfix.Result) -> set[str]:
    """Every violation key the last stop blocked on (its blocklog row), or an empty set on an allow."""
    if got.decision != "block":
        return set()
    path = fix.stem(".blocklog-%s.jsonl" % wlfix.ME)
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return {rows[-1]["key"], *rows[-1]["named"]}


def reason(got: wlfix.Result) -> str:
    try:
        doc = json.loads(got.out)
    except ValueError:
        return got.out
    return str(doc.get("reason") or "") + "\n" + str(doc.get("systemMessage") or "")


def test_sc5_an_item_on_the_pr_plans_epic_blocks(wl):  # noqa: F811
    own = loop_world(wl)
    plant_item(wl, "aaaa0001", "(deadbeef) the PR plan's own item")
    epic_for(wl, own.rsplit("/", 1)[-1], "aaaa0001")
    got = run_stop(wl)
    assert "open-items" in keys_of(wl, got), reason(got)[:1500]
    assert PR_SCOPE in got.out, got.out[:1500]
    assert "PR #543 works PLAN-pr-own.md." in got.out, got.out[:1500]


def test_sc5_control_the_same_item_on_an_epic_without_plan_is_queued(wl):  # noqa: F811
    loop_world(wl)
    plant_item(wl, "aaaa0001", "(deadbeef) the PR plan's own item")
    got_epic = wl.cli("--epic", wlfix.ME, "new", "an epic with no plan")
    found = re.search(r"epic #([0-9a-f]+)", got_epic.out)
    assert found, got_epic.out
    eid = found.group(1)
    assert wl.cli("--epic", wlfix.ME, "add", eid, "aaaa0001").rc == 0
    got = run_stop(wl)
    assert "open-items" not in keys_of(wl, got), reason(got)[:1500]
    assert (
        "Queued, not blocking: 1 item(s), 1 other plan(s); next: PLAN-queued-next.md." in got.out
    ), got.out[:1500]


def test_sc5_the_queued_line_never_enumerates_other_plans(wl):  # noqa: F811
    loop_world(wl)
    for i in range(5):
        loop_plan(wl, "extra%d" % i, opened=3, done=0)
    got = run_stop(wl)
    out = reason(got) + got.out
    assert "PLAN-pr-own.md" in out, out[:1500]
    for i in range(5):
        assert "PLAN-extra%d.md" % i not in out, out[:2000]
    assert "more plan(s)" not in out, out[:2000]


def test_sc5_a_red_ci_on_the_live_branch_blocks_without_the_publish_ref(wl):  # noqa: F811
    loop_world(wl, red=True, ci_ref=True)
    got = run_stop(wl)
    assert "ci-red" in keys_of(wl, got), reason(got)[:1500]
    assert F.CI_RED in got.out, got.out[:1500]


def test_sc5_control_off_the_loop_the_red_ci_is_not_armed(wl):  # noqa: F811
    loop_world(wl, branch="feature-x", red=True, ci_ref=True)
    got = run_stop(wl)
    assert "ci-red" not in keys_of(wl, got), reason(got)[:1500]
    assert PR_SCOPE not in got.out, got.out[:1500]


def test_sc5_an_expired_default_outside_the_epic_still_blocks(wl):  # noqa: F811
    loop_world(wl)
    with wl.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "add",
                    "id": "dq000001",
                    "at": stamp(130),
                    "by": wlfix.ME,
                    "s": "?",
                    "o": wlfix.ME,
                    "t": "(deadbeef) ship it? DEFAULT: ship it",
                }
            )
            + "\n"
        )
    got = run_stop(wl)
    assert "defer-expired" in keys_of(wl, got), reason(got)[:1500]


def test_sc5_a_dead_lease_outside_the_epic_still_blocks(wl):  # noqa: F811
    loop_world(wl)
    plant_dead_lease(wl, "eeee0005", "bdead0001")
    got = run_stop(wl)
    assert "open-items" in keys_of(wl, got), reason(got)[:1500]
    assert "eeee0005" in got.out, got.out[:1500]


def test_sc5_a_missing_state_doc_blocks_at_the_early_band(wl):  # noqa: F811
    """STATE.md freshness is a loop duty at every band (ruling 1d): kept in full by PR_LOOP, where the cap wait keeps it only in the late band (test_wl_cap_wait c3)."""
    own = loop_world(wl)
    plant_item(wl, "aaaa0001", "(deadbeef) the PR plan's own item")
    epic_for(wl, own.rsplit("/", 1)[-1], "aaaa0001")
    wl.state_file().unlink()
    got = run_stop(wl)
    assert "agent-state" in keys_of(wl, got), reason(got)[:1500]


def test_sc5_dropped_checks_stand_down_and_are_named(wl):  # noqa: F811
    """Every key the full battery raises off the loop and the PR_LOOP profile does not keep is absent on the loop and named in the Stood down phrase."""
    std = wlfix.import_wl("wl_standdown")
    loop_world(wl, branch="feature-x")
    # A deferral with no DEFAULT raises `undefaulted`, which only the cap wait keeps.
    with wl.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "add",
                    "id": "un000001",
                    "at": stamp(10),
                    "by": wlfix.ME,
                    "s": "?",
                    "o": wlfix.ME,
                    "t": "(deadbeef) which colour should the button be",
                }
            )
            + "\n"
        )
    wl.say("work done, nothing left")
    off = keys_of(
        wl,
        wl.run(
            F.band_env(wl, 0) | {"PATH": "%s:%s" % (wl.base / "binonly", wl.env.get("PATH", ""))}
        ),
    )
    dropped = {
        k
        for k in off
        if not std.keeps(std.PR_LOOP, k, False, False) and not k.startswith(std.PREFIXES)
    }
    assert dropped, "SETUP: the off-loop run raised no key the PR_LOOP profile drops: %s" % off
    wl.git("switch", "-q", "-c", BRANCH)
    wl.say("work done, nothing left")
    got = wl.run(
        F.band_env(wl, 0) | {"PATH": "%s:%s" % (wl.base / "binonly", wl.env.get("PATH", ""))}
    )
    on = keys_of(wl, got)
    assert not (dropped & on), "kept on the loop although the profile drops them: %s" % (
        dropped & on
    )
    line = next(ln for ln in reason(got).splitlines() if PR_SCOPE in ln)
    for k in dropped:
        assert k.split(":", 1)[0] in line, (k, line)


def test_sc5_control_off_the_loop_runs_todays_battery(wl):  # noqa: F811
    loop_world(wl, branch="feature-x")
    plant_item(wl, "dddd0004", "(deadbeef) in no epic at all")
    got = run_stop(wl)
    assert "open-items" in keys_of(wl, got), reason(got)[:1500]
    assert PR_SCOPE not in got.out, got.out[:1500]


def test_sc5_control_focus_on_still_uses_the_focus_profile(wl):  # noqa: F811
    own = loop_world(wl)
    plant_item(wl, "aaaa0001", "(deadbeef) the PR plan's own item")
    epic_for(wl, own.rsplit("/", 1)[-1], "aaaa0001")
    F.focus_on(wl)
    got = run_stop(wl)
    assert "open-items" not in keys_of(wl, got), "FOCUS parks open-items: %s" % reason(got)[:1500]


def test_sc5_m1_without_open_items_in_the_keep_list_the_epic_item_stands_down(wl):  # noqa: F811
    own = loop_world(wl)
    plant_item(wl, "aaaa0001", "(deadbeef) the PR plan's own item")
    epic_for(wl, own.rsplit("/", 1)[-1], "aaaa0001")
    mutated_hook(wl, "wl_standdown.py", '        "open-items",\n', "")
    got = run_stop(wl)
    assert "open-items" not in keys_of(wl, got), (
        "m1: the epic case does not depend on the keep-list entry: %s" % reason(got)[:900]
    )


def test_sc5_m2_without_the_in_scope_predicate_the_queued_item_blocks(wl):  # noqa: F811
    loop_world(wl)
    plant_item(wl, "dddd0004", "(deadbeef) in no epic at all")
    got = run_stop(wl)
    assert "open-items" not in keys_of(wl, got), "SETUP: %s" % reason(got)[:900]
    mutated_hook(
        wl,
        "wl_checks.py",
        '    _in_scope = (lambda rec: rec["id"] in _scope_ids) if _on_loop else None\n',
        "    _in_scope = None\n",
    )
    got = run_stop(wl)
    assert "open-items" in keys_of(wl, got), (
        "m2: the queued case does not depend on the predicate: %s" % reason(got)[:900]
    )


ADOPTED_TEXT = """# PLAN: %(name)s fixture
Status: ready
Owner: deadbeef (adopted from cafe1234 2026-09-20)
Depends-On: no-dep

%(pad)s

## Tasks

- [ ] Rewrite the alpha subsystem onto the shared helper in one commit
- [ ] Regenerate the beta baseline with the audited token
"""


def adopted(fix, name: str) -> str:
    folder = fix.proj / "agent" / "plans"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ("PLAN-%s.md" % name)).write_text(
        ADOPTED_TEXT % {"name": name, "pad": F.PLAN_PAD * 3}, encoding="utf-8"
    )
    return "agent/plans/PLAN-%s.md" % name


def test_sc6_an_adopted_plan_outside_the_pr_gives_no_plan_adopted(wl):  # noqa: F811
    """The PLAN-stop-hook-retro-20260925 case of the dry run: adopted, untracked boxes, not the PR's plan."""
    loop_world(wl)
    adopted(wl, "retro-fixture")
    got = run_stop(wl)
    assert "plan-adopted" not in keys_of(wl, got), reason(got)[:1500]
    assert "PLAN-retro-fixture.md" not in got.out, got.out[:2000]


def test_sc6_control_the_same_adoption_on_the_pr_plan_blocks(wl):  # noqa: F811
    loop_world(wl)
    rel_ = adopted(wl, "retro-fixture")
    F.merged_nodes(wl, [pr_node("OPEN", "Plan: %s\n" % rel_)])
    got = run_stop(wl)
    assert "plan-adopted" in keys_of(wl, got), reason(got)[:1500]


def test_sc6_open_boxes_across_other_plans_give_no_plan_unimplemented(wl):  # noqa: F811
    loop_world(wl, opened=0)
    loop_plan(wl, "elsewhere", opened=4, done=0)
    got = run_stop(wl)
    assert "plan-unimplemented" not in keys_of(wl, got), reason(got)[:1500]


def test_sc6_control_one_open_box_on_the_pr_plan_blocks_and_is_named(wl):  # noqa: F811
    loop_world(wl, opened=1)
    got = run_stop(wl)
    assert "plan-unimplemented" in keys_of(wl, got), reason(got)[:1500]
    assert "T0 the open pr-own fixture box" in got.out, got.out[:2000]
    assert "PLANNED BUT NOT IMPLEMENTED" not in got.out, got.out[:2000]


def test_sc6_the_same_box_with_a_live_background_task_is_an_advisory(wl):  # noqa: F811
    loop_world(wl, opened=1)
    wl.bg = json.dumps(
        [{"id": "bw9", "type": "shell", "status": "running", "description": "ci-trace --wait"}]
    )
    got = run_stop(wl)
    assert "plan-unimplemented" not in keys_of(wl, got), reason(got)[:1500]


def test_sc10_the_plan_adopted_recipe_survives_a_quote_in_the_box_text(wl):  # noqa: F811
    """The 2026-10-03 recipe broke the shell when copied: a box text opening with `("` sat inside a hand-made "..." quote. The printed --add line must parse back to the exact box text."""
    import shlex  # noqa: PLC0415 -- local to the one test that needs it

    loop_world(wl)
    rel_ = adopted(wl, "quote-fixture")
    path = wl.proj / rel_
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "- [ ] Rewrite the alpha subsystem onto the shared helper in one commit",
            '- [ ] ("R1 A writer\'s paths stay subtracted while any item is leased',
        ),
        encoding="utf-8",
    )
    F.merged_nodes(wl, [pr_node("OPEN", "Plan: %s\n" % rel_)])
    got = run_stop(wl)
    lines = [ln for ln in reason(got).splitlines() if "worklist.py --add" in ln]
    assert lines, reason(got)[:1500]
    argvs = [shlex.split(ln) for ln in lines]
    assert any(
        a[-1].startswith('("R1 A writer\'s paths stay subtracted') for a in argvs
    ), argvs
