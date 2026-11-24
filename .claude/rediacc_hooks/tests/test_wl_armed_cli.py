"""Armed actions, the verbs (agent/plans/PLAN-armed-actions.md box AA2): `--arm`, `--disarm`, `--armed-start`, `--armed-list`, `--arm-from-survey`, and `--state` passing the live arms.

Every refusal is paired with the accepted run one token away, so a verb that refused everything would fail the controls, and every refusal is checked to have written nothing to the store.
"""

from __future__ import annotations

import datetime
import json
import re
import time

from rediacc_hooks.tests import wlfix

ME = wlfix.ME


def soon(hours=2):
    when = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=hours)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def ago(minutes):
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=minutes)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def add(wl, text="held landing (deadbeef)"):
    got = wl.cli("--add", ME, text)
    assert got.rc == 0, got.err
    return re.search(r"added #([0-9a-f]+)", got.out).group(1)


def events(wl, kind):
    return [e for e in map(json.loads, wl.wl_events().splitlines()) if e.get("ev") == kind]


def plant(wl, **ev):
    """Append one event as another writer would (the Stop hook's latch, a queue lease)."""
    ev.setdefault("at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    ev.setdefault("by", ME)
    ev.setdefault("ns", time.time_ns())
    with (wl.store_dir / "zz-planted.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(ev) + "\n")


def item_events(wl):
    """Every store event except the markdown-inbox sync a first load appends, which is not an item write."""
    return [e for e in map(json.loads, wl.wl_events().splitlines()) if e.get("ev") != "md"]


def refused(wl, needle, *argv):
    before = item_events(wl)
    got = wl.cli(*argv)
    assert got.rc != 0, "accepted: %s" % got.out
    assert needle in got.err, got.err
    assert item_events(wl) == before, "a refusal wrote to the store"
    return got


def lastevent(wl, running):
    wl.stem(".lastevent-%s.json" % ME).write_text(
        json.dumps({"background_tasks": [{"id": t, "status": "running"} for t in running]}),
        encoding="utf-8",
    )


def test_arm_writes_one_arm_event_of_the_design_shape(wl):
    rid = add(wl)
    nb = soon()
    got = wl.cli(
        "--arm", ME, rid, "--when", "NOT-BEFORE:%s" % nb, "--run-cmd", "./run.sh worktree land L1"
    )
    assert got.rc == 0, got.err
    assert "armed #%s" % rid in got.out
    arms = events(wl, "arm")
    assert len(arms) == 1
    ev = arms[0]
    assert set(ev) >= {"ev", "id", "at", "by", "aid", "when", "run", "cmd", "sha", "lease", "exp"}
    assert ev["id"] == rid
    assert ev["when"] == ["NOT-BEFORE:%s" % nb]
    assert ev["cmd"] == "./run.sh worktree land L1"
    assert ev["run"] == ""
    assert re.fullmatch(r"[0-9a-f]{8}", ev["aid"])
    # A time arm expires 24 h after its latest NOT-BEFORE.
    want = datetime.datetime.strptime(nb, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.UTC
    ) + datetime.timedelta(hours=24)
    assert ev["exp"] == want.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_arm_with_a_brief_records_its_sha_and_names_the_commit_line(wl):
    rid = add(wl)
    brief = wl.proj / "agent" / ME / "armed" / ("%s.md" % rid)
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text("worklist.py --armed-start deadbeef %s\n\nland it\n" % rid, encoding="utf-8")
    rel = "agent/%s/armed/%s.md" % (ME, rid)
    got = wl.cli("--arm", ME, rid, "--when", "PUSHED:head", "--run", rel)
    assert got.rc == 0, got.err
    assert "git add -- %s" % rel in got.out
    ev = events(wl, "arm")[0]
    assert ev["run"] == rel
    assert re.fullmatch(r"[0-9a-f]{12}", ev["sha"])


def test_arm_refuses_a_brief_that_is_missing_or_misplaced(wl):
    rid = add(wl)
    refused(
        wl,
        "cannot be read",
        "--arm",
        ME,
        rid,
        "--when",
        "PUSHED:head",
        "--run",
        "agent/%s/armed/%s.md" % (ME, rid),
    )
    refused(
        wl,
        "must name the item's brief path",
        "--arm",
        ME,
        rid,
        "--when",
        "PUSHED:head",
        "--run",
        "/tmp/brief.md",
    )
    refused(wl, "exactly one of", "--arm", ME, rid, "--when", "PUSHED:head")


def test_past_not_before_is_refused_and_a_future_one_accepted(wl):
    rid = add(wl)
    refused(
        wl,
        "not in the future",
        "--arm",
        ME,
        rid,
        "--when",
        "NOT-BEFORE:%s" % ago(5),
        "--run-cmd",
        "x",
    )
    assert wl.cli("--arm", ME, rid, "--when", "NOT-BEFORE:%s" % soon(), "--run-cmd", "x").rc == 0


def test_unknown_ticked_item_is_refused_and_a_known_one_accepted(wl):
    rid = add(wl)
    other = add(wl, "the blocker (deadbeef)")
    refused(wl, "names no item", "--arm", ME, rid, "--when", "TICKED:#feedfeed", "--run-cmd", "x")
    got = wl.cli("--arm", ME, rid, "--when", "TICKED:#%s" % other, "--run-cmd", "x")
    assert got.rc == 0, got.err


def test_exit_of_a_task_not_running_is_refused_and_a_running_one_accepted(wl):
    rid = add(wl)
    refused(wl, "unreadable", "--arm", ME, rid, "--when", "EXIT:bxyz123", "--run-cmd", "x")
    lastevent(wl, ["bother99"])
    refused(wl, "not listed running", "--arm", ME, rid, "--when", "EXIT:bxyz123", "--run-cmd", "x")
    lastevent(wl, ["bxyz123"])
    assert wl.cli("--arm", ME, rid, "--when", "EXIT:bxyz123", "--run-cmd", "x").rc == 0


def test_needs_none_is_refused_and_needs_sugar_resolves(wl):
    rid = add(wl)
    refused(wl, "waits on nothing", "--arm", ME, rid, "--when", "NEEDS:none", "--run-cmd", "x")
    assert wl.cli("--arm", ME, rid, "--when", "NEEDS:pushed-head", "--run-cmd", "x").rc == 0
    assert events(wl, "arm")[0]["when"] == ["PUSHED:head"]


def test_a_second_live_arm_is_refused_until_disarmed(wl):
    rid = add(wl)
    assert wl.cli("--arm", ME, rid, "--when", "PUSHED:head", "--run-cmd", "x").rc == 0
    refused(
        wl,
        "already carries a live arm",
        "--arm",
        ME,
        rid,
        "--when",
        "BENCH:deployed",
        "--run-cmd",
        "x",
    )
    refused(wl, "--why", "--disarm", ME, rid)
    got = wl.cli("--disarm", ME, rid, "--why", "replanned")
    assert got.rc == 0, got.err
    assert wl.cli("--arm", ME, rid, "--when", "BENCH:deployed", "--run-cmd", "x").rc == 0


def test_an_item_leased_worker_queue_is_refused_and_names_the_release(wl):
    rid = add(wl)
    plant(wl, ev="lease", id=rid, until=soon(1), worker="queue", note="HELD_BY:PLAN-x.md")
    got = refused(wl, "worker:queue", "--arm", ME, rid, "--when", "PUSHED:head", "--run-cmd", "x")
    assert "--lease %s %s release" % (ME, rid) in got.err
    # Control: the same item leased to a real worker arms.
    plant(wl, ev="lease", id=rid, until=soon(1), worker="a0123456789abcdef")
    assert wl.cli("--arm", ME, rid, "--when", "PUSHED:head", "--run-cmd", "x").rc == 0


def test_lease_on_a_held_lease_is_refused_and_an_unheld_one_accepted(wl):
    rid = add(wl)
    holds = wl.proj / ".git" / "rediacc-worktrees"
    holds.mkdir(parents=True, exist_ok=True)
    (holds / "L1.hold").write_text(
        json.dumps({"item": rid, "reason": "recordings"}), encoding="utf-8"
    )
    got = refused(
        wl,
        "`.hold` record",
        "--arm",
        ME,
        rid,
        "--when",
        "PUSHED:head",
        "--run-cmd",
        "x",
        "--lease",
        "L1",
    )
    assert "./run.sh worktree unhold L1" in got.err
    assert (
        wl.cli("--arm", ME, rid, "--when", "PUSHED:head", "--run-cmd", "x", "--lease", "L2").rc == 0
    )
    assert events(wl, "arm")[0]["lease"] == "L2"


def test_another_sessions_item_is_refused(wl):
    got = wl.cli_as("cafe1234", "--add", "cafe1234", "a peer's item (cafe1234)")
    rid = re.search(r"added #([0-9a-f]+)", got.out).group(1)
    refused(
        wl,
        "never arm another session's tracking",
        "--arm",
        ME,
        rid,
        "--when",
        "PUSHED:head",
        "--run-cmd",
        "x",
    )


def test_expires_bounds(wl):
    rid = add(wl)
    refused(
        wl,
        "between +1 and +168",
        "--arm",
        ME,
        rid,
        "--when",
        "PUSHED:head",
        "--run-cmd",
        "x",
        "--expires",
        "+200",
    )
    refused(
        wl,
        "could never fire",
        "--arm",
        ME,
        rid,
        "--when",
        "NOT-BEFORE:%s" % soon(5),
        "--run-cmd",
        "x",
        "--expires",
        "+2",
    )
    assert (
        wl.cli("--arm", ME, rid, "--when", "PUSHED:head", "--run-cmd", "x", "--expires", "+48").rc
        == 0
    )


def test_armed_start_is_refused_before_the_fire_and_accepted_after(wl):
    rid = add(wl)
    assert (
        wl.cli(
            "--arm", ME, rid, "--when", "PUSHED:head", "--run-cmd", "./run.sh worktree land L1"
        ).rc
        == 0
    )
    refused(wl, "has not fired", "--armed-start", ME, rid)
    aid = events(wl, "arm")[0]["aid"]
    plant(wl, ev="armfire", id=rid, aid=aid, v="fired", why="PUSHED:head: HEAD is on its upstream")
    got = wl.cli("--armed-start", ME, rid)
    assert got.rc == 0, got.err
    assert "next: ./run.sh worktree land L1" in got.out
    starts = events(wl, "armstart")
    assert [(e["id"], e["aid"]) for e in starts] == [(rid, aid)]
    # Consumed: a second start finds no live arm.
    refused(wl, "no live arm", "--armed-start", ME, rid)


def test_armed_start_refuses_an_expired_arm_and_names_the_rearm(wl):
    rid = add(wl)
    assert wl.cli("--arm", ME, rid, "--when", "PUSHED:head", "--run-cmd", "x").rc == 0
    aid = events(wl, "arm")[0]["aid"]
    plant(wl, ev="armfire", id=rid, aid=aid, v="expired", why="expired")
    got = refused(wl, "is expired", "--armed-start", ME, rid)
    assert "--disarm %s %s" % (ME, rid) in got.err


def test_armed_list_names_each_live_arm(wl):
    assert "no live arms" in wl.cli("--armed-list", ME).out
    rid = add(wl)
    assert wl.cli("--arm", ME, rid, "--when", "PUSHED:head", "--run-cmd", "x").rc == 0
    out = wl.cli("--armed-list", ME).out
    assert "#%s" % rid in out
    assert "armed" in out
    assert "PUSHED:head" in out


SURVEY = """# writers-now survey

## 9. Something else

| a | b |

## 10. Armed

| blocker | dependent sigs | trigger | brief draft path |
|---|---|---|---|
| AA1 | 26dc6529 da7de199 | `NOT-BEFORE:%s` | %s |
| live bench deploy | ec0a85bb | `NEEDS:pushed-head` | %s |
"""


def test_arm_from_survey_turns_two_rows_into_two_items_briefs_and_arms(wl):
    d1 = wl.base / "draft1.md"
    d2 = wl.base / "draft2.md"
    d1.write_text("start AA3 now\n", encoding="utf-8")
    d2.write_text("run the bench step\n", encoding="utf-8")
    survey = wl.base / "survey.md"
    survey.write_text(SURVEY % (soon(), d1, d2), encoding="utf-8")
    got = wl.cli("--arm-from-survey", ME, str(survey))
    assert got.rc == 0, got.err
    arms = events(wl, "arm")
    assert len(arms) == 2
    adds = [e for e in events(wl, "add") if e["id"] in {a["id"] for a in arms}]
    assert len(adds) == 2
    assert all("(%s)" % ME in e["t"] for e in adds)
    for arm in arms:
        brief = wl.proj / arm["run"]
        text = brief.read_text(encoding="utf-8")
        assert text.splitlines()[0].endswith("--armed-start %s %s" % (ME, arm["id"]))
        assert arm["sha"]
    assert sorted(a["when"][0].split(":")[0] for a in arms) == ["NOT-BEFORE", "PUSHED"]


def test_arm_from_survey_writes_nothing_when_one_row_is_bad(wl):
    d1 = wl.base / "draft1.md"
    d1.write_text("x\n", encoding="utf-8")
    survey = wl.base / "survey.md"
    survey.write_text(SURVEY % (soon(), d1, wl.base / "missing.md"), encoding="utf-8")
    refused(wl, "cannot be read", "--arm-from-survey", ME, str(survey))
    survey.write_text("# no armed section\n", encoding="utf-8")
    refused(wl, "no `## Armed` section", "--arm-from-survey", ME, str(survey))


def test_state_refuses_a_body_without_armed_while_an_arm_is_live(wl):
    # Control first: no live arm, the canonical body is accepted.
    got = wl.cli("--state", ME, stdin=wlfix.STATE_BODY)
    assert got.rc == 0, got.err
    rid = add(wl)
    assert wl.cli("--arm", ME, rid, "--when", "PUSHED:head", "--run-cmd", "x").rc == 0
    got = wl.cli("--state", ME, stdin=wlfix.STATE_BODY)
    assert got.rc != 0, got.out
    assert "unarmed" in got.err, got.err
    body = wlfix.STATE_BODY + "\n\n## Armed\n- #%s lands L1 once HEAD is pushed\n" % rid
    got = wl.cli("--state", ME, stdin=body)
    assert got.rc == 0, got.err
