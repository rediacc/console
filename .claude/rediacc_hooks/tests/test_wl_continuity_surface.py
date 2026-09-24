"""The blocked stop surfaces what the hook already computed (agent/plans/PLAN-stop-hook-continuity.md, P0).

Operator ruling 2026-09-24 (/ask), "One quoted + others named": a blocked stop quotes ONE rotating check in full and NAMES every other outstanding one, plus a digest of the queued advisories. Before it, the rotating tail was a bare count and the advisory queue was a bare count, so N outstanding checks cost N full turns and a busy session never saw a queued advisory at all.

Every case drives the real hook through `wlfix`, the way test_wl_roster.py does.
"""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

if TYPE_CHECKING:
    import pathlib


def state_path(fix) -> pathlib.Path:
    return fix.stem(".state-deadbeef.json")


def load_state(fix) -> dict:
    path = state_path(fix)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def plant_outq(fix, items: list[dict]) -> None:
    """Seed the advisory queue directly in the state document, the way a producer on an earlier stop would have left it."""
    doc = load_state(fix)
    doc["outq"] = {"seq": len(items), "items": items, "shown": {}}
    state_path(fix).write_text(json.dumps(doc), encoding="utf-8")


def three_rotating(fix) -> None:
    """Three rotating checks at once: an open item, no '## Remaining' section, and a stale handover document."""
    fix.env["WORKLIST_STUCK_ROUNDS"] = "99"
    fix.brief_now()
    fix.add_item("- [ ] (deadbeef) open thing")
    fix.say("answer with no remaining section")


def test_p01_the_first_block_names_every_rotating_check(wl):  # noqa: F811
    """CONTROL: before P0.1 the first block carried ONE rotating check plus "N more check(s) outstanding"; the others were unnamed until later stops."""
    three_rotating(wl)
    got = wl.run()
    assert got.decision == "block", got.out[:400]
    reason = json.loads(got.out)["reason"]
    assert "ALSO OUTSTANDING, NAMED" in reason, reason[:800]
    named = reason.split("ALSO OUTSTANDING, NAMED", 1)[1]
    keys = [ln.strip().split(":", 1)[0] for ln in named.splitlines()[1:] if ln.startswith("    ")]
    assert len(keys) >= 2, "P0.1: fewer than two rotating checks were named: %s" % named[:600]
    assert "open-items" in keys or "OPEN worklist item" in reason, reason[:800]
    assert "more check(s) outstanding, each named above" in reason, reason[-400:]


def test_p01_only_the_quoted_check_rotates_and_the_named_ones_follow(wl):  # noqa: F811
    """The LRU rotation is unchanged: the second stop quotes a check the first stop only named."""
    three_rotating(wl)
    first = json.loads(wl.run().out)["reason"]
    wl.newturn()
    wl.say("answer with no remaining section")
    second = json.loads(wl.run().out)["reason"]
    quoted_first = first.split("ALSO OUTSTANDING, NAMED", 1)[0]
    quoted_second = second.split("ALSO OUTSTANDING, NAMED", 1)[0]
    assert quoted_first != quoted_second, "P0.1: the same check was quoted on both stops"


def test_p01_inverse_a_single_rotating_check_names_nothing(wl):  # noqa: F811
    """INVERSE: with one rotating check there is nothing to name, and the footer says so."""
    wl.env["WORKLIST_STUCK_ROUNDS"] = "99"
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) open thing")
    wl.say("answer\n\n## Remaining\n- the open thing (pending, mine)")
    got = wl.run()
    assert got.decision == "block", got.out[:400]
    reason = json.loads(got.out)["reason"]
    assert "ALSO OUTSTANDING, NAMED" not in reason, reason[:600]
    assert "no other checks are outstanding" in reason, reason[-300:]


def outq_entry(key: str, text: str, prio: int, seq: int, sticky: bool = False) -> dict:
    sig = "%012x" % seq
    return {
        "key": "%s:%s" % (key, sig) if sticky else key,
        "prio": prio,
        "sticky": sticky,
        "sig": sig,
        "text": text,
        "at": "2026-09-24T00:00:00Z",
        "seq": seq,
    }


def test_p02_a_blocked_stop_carries_the_advisory_digest(wl):  # noqa: F811
    """CONTROL: before P0.2 the block said only "N advisory section(s) are queued and CANNOT be shown"."""
    three_rotating(wl)
    wl.run()  # first stop builds the state document
    plant_outq(
        wl,
        [
            outq_entry(
                "claim-check",
                "CLAIM CHECK: #abcd1234 evidence does not show the claim.",
                0,
                1,
                True,
            ),
            outq_entry(
                "plan-tasks", "PLAN TASKS: 3 open box(es)\n  - [ ] box one\n  - [ ] box two", 2, 2
            ),
        ],
    )
    wl.newturn()
    wl.say("answer with no remaining section")
    got = wl.run()
    reason = json.loads(got.out)["reason"]
    assert "QUEUED ADVISORIES" in reason, reason[-800:]
    assert "CLAIM CHECK: #abcd1234" in reason, reason[-800:]
    assert "plan-tasks: PLAN TASKS: 3 open box(es)" in reason, reason[-800:]
    assert "claim-check: CLAIM CHECK" in reason, (
        "the sticky key's :sig suffix leaked: %s" % reason[-800:]
    )
    assert "CANNOT be shown" not in reason


def test_p02_a_one_line_advisory_is_delivered_and_a_body_stays_queued(wl):  # noqa: F811
    """The one-line advisory is DELIVERED by the digest and leaves the queue; the multi-line body is only named and waits for a clean stop."""
    three_rotating(wl)
    wl.run()
    plant_outq(
        wl,
        [
            outq_entry(
                "claim-check",
                "CLAIM CHECK: #abcd1234 evidence does not show the claim.",
                0,
                1,
                True,
            ),
            outq_entry("plan-tasks", "PLAN TASKS: 3 open box(es)\n  - [ ] box one", 2, 2),
        ],
    )
    wl.newturn()
    wl.say("answer with no remaining section")
    wl.run()
    keys = [e["key"] for e in load_state(wl)["outq"]["items"]]
    assert "plan-tasks" in keys, keys
    assert not any(k.startswith("claim-check") for k in keys), keys
    wl.newturn()
    wl.say("answer with no remaining section")
    third = json.loads(wl.run().out)["reason"]
    assert "CLAIM CHECK" not in third, "the delivered one-liner was shown twice: %s" % third[-600:]
    assert "plan-tasks: PLAN TASKS" in third, third[-600:]


def test_p02_the_digest_is_capped_at_six_lines(wl):  # noqa: F811
    """At most six sections are named; the rest are counted, never dropped."""
    three_rotating(wl)
    wl.run()
    plant_outq(wl, [outq_entry("adv%d" % i, "body %d\nmore" % i, 2, i) for i in range(1, 10)])
    wl.newturn()
    wl.say("answer with no remaining section")
    reason = json.loads(wl.run().out)["reason"]
    digest = reason.split("QUEUED ADVISORIES", 1)[1]
    assert sum(1 for i in range(1, 10) if "adv%d: body %d" % (i, i) in digest) == 6, digest[:800]
    assert "(+3 more queued)" in digest, digest[:800]
    assert len(load_state(wl)["outq"]["items"]) == 9


def test_p04_a_blocked_stop_records_an_admission_in_tier_r(wl):  # noqa: F811
    """CONTROL: before P0.4 the prefilter and its Tier R record sat after the block exit, so a blocked stop whose turn admits a mistake left no row at all."""
    three_rotating(wl)
    wl.say("I clobbered the file another session was editing.")
    got = wl.run()
    assert got.decision == "block", got.out[:300]
    log = wl.base / "tmp" / "claude-worklist" / (wl.wl.name + ".admissions-deadbeef.jsonl")
    assert log.is_file(), "P0.4: no Tier R row on a blocked stop"
    rows = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(rows) == 1, rows
    assert rows[0]["families"], rows
    wl.run()
    rows = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(rows) == 1, "the same turn was recorded twice across two blocked stops: %s" % rows


def test_p04_inverse_a_blocked_stop_without_an_admission_writes_nothing(wl):  # noqa: F811
    three_rotating(wl)
    wl.run()
    assert not (wl.wl.parent / (wl.wl.name + ".admissions-deadbeef.jsonl")).exists()


def test_p05_the_block_footer_names_the_hint_propose_outlet(wl):  # noqa: F811
    """CONTROL: before P0.5 the footer ordered a fix and offered no way to record a misfire that cannot be fixed this turn."""
    three_rotating(wl)
    reason = json.loads(wl.run().out)["reason"]
    assert "worklist.py --hint-propose deadbeef '<lesson>' SOURCE: <check-key>" in reason, reason[
        -500:
    ]


AGENT = "a1234567890abcdef"
REPORT_ID = AGENT[-12:]


def plant_report(fix, silent: bool = False) -> None:
    """One report, captured an hour ago, which is past the invariant age of `unread-reports`."""
    store = fix.base / "reports"
    (store / "agenttest").mkdir(parents=True, exist_ok=True)
    (store / "agenttest" / "r.md").write_text("A WRITER'S FINDING\nbody", encoding="utf-8")
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
    entry = {
        "ev": "report",
        "id": REPORT_ID,
        "at": at,
        "branch": "agenttest",
        "agent": "writer",
        "type": "general-purpose",
        "session": "deadbeef",
        "body": "agenttest/r.md",
        "bytes": 900,
        "silent": silent,
        "sends": 0 if silent else 1,
        "title": "A WRITER'S FINDING",
        "transcript": "",
        "src": "hook",
    }
    (store / "index.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")


def plant_notification(fix, result: str, minutes_ago: float = 59) -> None:
    """The lead-transcript record the harness writes when a sub-agent stops."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - minutes_ago * 60))
    text = (
        "<task-notification>\n<task-id>%s</task-id>\n<status>completed</status>\n"
        "<summary>Agent finished</summary>\n<result>%s</result>\n</task-notification>"
        % (AGENT, result)
    )
    fix.append_transcript({"type": "user", "timestamp": stamp, "message": {"content": text}})


def quiet_world(fix) -> None:
    fix.brief_now()
    fix.hand_now()
    fix.say("done\n\n## Remaining\n- nothing")


def test_p15_a_report_the_lead_already_received_is_read_automatically(wl):  # noqa: F811
    """CONTROL: before P1.5 the report blocked as unread although the lead's transcript already held its completed notification with the full result."""
    quiet_world(wl)
    plant_report(wl)
    plant_notification(wl, "The fix landed at wl_roster.py:412.")
    got = wl.run()
    assert "UNREAD SUB-AGENT REPORTS" not in got.out, got.out[:800]
    marks = (wl.base / "reports" / "read.jsonl").read_text(encoding="utf-8")
    assert '"via":"task-notification"' in marks, marks


def test_p15_inverse_without_the_notification_it_still_blocks(wl):  # noqa: F811
    quiet_world(wl)
    plant_report(wl)
    got = wl.run()
    assert "UNREAD SUB-AGENT REPORTS" in got.out, got.out[:800]


def test_p15_inverse_a_silent_report_is_never_read_automatically(wl):  # noqa: F811
    """An empty `<result>` is the [SILENT] shape, which stays a real signal."""
    quiet_world(wl)
    plant_report(wl, silent=True)
    plant_notification(wl, "")
    got = wl.run()
    assert "UNREAD SUB-AGENT REPORTS" in got.out, got.out[:800]


def state_naming(fix, item: str) -> None:
    body = wlfix.STATE_BODY.replace(
        "Push and watch the run,", "Finish #%s, then push and watch the run," % item
    )
    got = fix.cli("--state", wlfix.ME, stdin=body)
    assert got.rc == 0, got.err[:300]


def added(result) -> str:
    found = re.search(r"#([0-9a-f]+)", result.out)
    assert found, "--add printed no item id: %r" % result.out[:200]
    return found.group(1)


def test_p12_a_commit_does_not_stale_state_md(wl):  # noqa: F811
    """CONTROL for P1.2: `state_world_sig` carried HEAD, so every commit staled a 16-minute-old document. The owned item set and the items `## Next action` names are the only triggers now."""
    wl.reg_repo()
    wl.brief_now()
    ident = added(wl.cli("--add", wlfix.ME, "the named item"))
    wl.cli("--lease", wlfix.ME, ident, "+60", "worker:lead-shell", "driving it")
    state_naming(wl, ident)
    wl.say("working\n\n## Remaining\n- #%s in flight" % ident)
    wl.run()
    wl.age_state(wlfix.ME, 16)
    wl.fixcommit("src/a.txt", "fix: a commit that moves HEAD")
    wl.newturn()
    wl.say("working\n\n## Remaining\n- #%s in flight" % ident)
    got = wl.run()
    assert "STATE.md is stale" not in got.out, got.out[:800]


def test_p12_inverse_ticking_the_named_item_stales_it(wl):  # noqa: F811
    """The staleness check runs only while something remains, so a pending harness task keeps the session busy after the tick."""
    wl.brief_now()
    wl.task(7, "pending", "the next thing")
    ident = added(wl.cli("--add", wlfix.ME, "the named item"))
    state_naming(wl, ident)
    wl.say("working\n\n## Remaining\n- #%s open" % ident)
    wl.run()
    wl.age_state(wlfix.ME, 16)
    ticked = wl.cli("--tick", wlfix.ME, ident, "done, suite exit code 0")
    assert ticked.rc == 0, ticked.err[:300]
    wl.newturn()
    wl.say("done\n\n## Remaining\n- #7 the next thing (pending)")
    got = wl.run({"WORKLIST_FOCUS": "off"})
    assert "STATE.md is stale" in got.out, got.out[:800]


def test_p12_post_compact_carries_the_computed_facts(wl):  # noqa: F811
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) an open thing for the slice")
    out = wl.post_compact().out
    assert "=== computed facts" in out, out[:600]
    assert "an open thing for the slice" in out, out[:1200]
