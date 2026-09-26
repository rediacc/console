"""Per-agent bootstrap and adoption, detached HEAD, trap headings, supervised leases, and the focused one-check-per-stop rotation.

Ported from `.claude/hooks/stop/worklist-cases/12-agent-docs-and-focus.sh`, one pytest function per numbered bash case, and one more wherever a bash block called `setup` again mid-case. Where two labelled bash cases shared one fixture (153b2 with 153b3, 154a with 154b) the sequence is kept inside a single function, because the second half asserts against a world the first half
built.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from typing import TYPE_CHECKING

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_ci_status import ci_job, ci_rollup, ci_run, ci_setup
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

if TYPE_CHECKING:
    import pathlib

CRONS_WITH_PROMPTS = json.dumps(
    [
        {
            "id": "w",
            "schedule": "17 * * * *",
            "prompt": "HOURLY LOOP fixture: advance the campaign.",
        },
    ]
)

CRONS_BROKEN = json.dumps(
    [
        {"id": "w", "schedule": "not a cron", "prompt": "BROKEN fixture."},
    ]
)

CRONS_VALID = json.dumps(
    [
        {"id": "w", "schedule": "17 * * * *", "prompt": "HOURLY LOOP fixture."},
    ]
)


def stamp(minutes_ago: float = 0.0, fmt: str = "%Y-%m-%dT%H:%M:%SZ") -> str:
    """A UTC stamp `minutes_ago` in the past, in the format the bash `date -u -d` calls produced."""
    return time.strftime(fmt, time.gmtime(time.time() - minutes_ago * 60))


def plant_event(fix, payload: dict) -> None:
    """Append one raw event to the legacy log."""
    with fix.events.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def added_id(result: wlfix.Result) -> str:
    """The item id `--add` printed."""
    found = re.search(r"^added #([0-9a-f]+)", result.out, re.MULTILINE)
    assert found, "--add printed no item id: %r" % result.out[:200]
    return found.group(1)


def age_file(path: pathlib.Path, minutes_ago: float) -> None:
    """The bash `touch -d '<n> minutes ago'`: an UNSTAMPED planted document is judged by its mtime, which is the fallback these adoption cases are about."""
    when = time.time() - minutes_ago * 60
    os.utime(path, (when, when))


def state_doc(fix) -> dict:
    """The per-session state document the hook banks its signatures in."""
    path = fix.stem(".state-deadbeef.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def test_153a_a_missing_agent_dir_blocks_with_the_bootstrap_once_as_a_wall(wl):  # noqa: F811
    """T1/T2, decision 5: block with the exact bootstrap commands, NEVER auto-create (the RULES.md copy-forward is a judgement call a hook must not make). The WALL is shown once per branch per session, latched on agent_boot_told; the follow-up is a one-liner that keeps blocking without repeating itself."""
    wl.brief_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    shutil.rmtree(wl.proj / "agent" / "deadbeef")

    got = wl.run()
    assert '"decision": "block"' in got.out, got.out[:200]
    assert "mkdir -p agent/deadbeef" in got.out, got.out[:200]
    assert "RULES.md" in got.out, got.out[:200]
    assert not (wl.proj / "agent" / "deadbeef").is_dir(), (
        "T1: the hook AUTO-CREATED the session dir (decision 5 violated)"
    )

    wl.newturn()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    second = wl.run()
    assert '"decision": "block"' in second.out, second.out[:200]
    assert "still absent" in second.out, second.out[:200]
    assert "mkdir -p agent/deadbeef" not in second.out, (
        "T2: the wall was repeated on the second stop: %s" % second.out[:200]
    )

    # SILENT control: with the dir restored and a fresh STATE.md the wall is gone. The world is moved first (task 8) or the third consecutive unmoved stop would trip the STUCK detector and this control would test the wrong gate.
    (wl.proj / "agent" / "deadbeef").mkdir(parents=True, exist_ok=True)
    wl.task(8, "pending", "moved")
    wl.hand_now()
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)\n- #8 moved (pending)")
    wl.check("allow", "", "T1 CONTROL: dir present plus a fresh STATE.md allows, no bootstrap text")


def test_153b_t7a_an_unsigned_thirty_minute_document_is_adopted(wl):  # noqa: F811
    """A second session arriving on a branch has no recorded signature for the document the first session wrote; the old pure-age fallback would order an immediate rewrite, reproducing the churn the redesign fixes. Adoption is bounded (60m) and fires ONLY on an "ok" verdict."""
    wl.brief_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.plant_state(wlfix.STATE_BODY)  # planted: NO signature banked
    age_file(wl.state_file(), 30)

    wl.check("allow", "", "T7a: an unsigned 30-minute document is ADOPTED, not rewritten")
    assert state_doc(wl).get("state_sig"), "T7a: no state_sig was banked on the ok verdict"


def test_153b_t7b_an_unsigned_ninety_minute_document_stays_stale(wl):  # noqa: F811
    """Banking the signature on a "stale" verdict would let the next stop compare cur_sig against a signature recorded DURING the block and allow: a gate that clears itself without a rewrite. T7b is the anti-vacuity control, and it must block TWICE running."""
    wl.brief_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.plant_state(wlfix.STATE_BODY)
    age_file(wl.state_file(), 90)

    wl.check(
        "block",
        "STATE.md is stale",
        "T7b FIRE: an unsigned 90-minute document is past the adopt horizon",
    )
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.check(
        "block", "STATE.md is stale", "T7b ANTI-VACUITY: it blocks AGAIN on an unchanged world"
    )
    assert not state_doc(wl).get("state_sig"), (
        "T7b: the stale path banked a signature (the gate would clear itself)"
    )

    # Move the world (task 8) before the control stop, or the fourth consecutive unmoved stop trips the STUCK detector instead of testing this gate.
    wl.task(8, "pending", "moved")
    wl.hand_now()
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)\n- #8 moved (pending)")
    wl.check("allow", "", "T7b CONTROL: a real --state rewrite clears it")


def test_153b2_a_peers_item_does_not_stale_my_document_but_my_own_does(wl):  # noqa: F811
    """C12, the v18 bug this pins. state_world_sig hashed EVERY item regardless of owner, so with ~48 agents in one worktree any peer --add/--tick moved the key. A check whose contract is "an unchanged world never stales it" then degenerated into "fires every 15 minutes", indistinguishable from wall-clock at the point of observation, which is what made the WRONG fix (raise the
    limit) look obvious. v17 had already scoped world_sig this way; state_world_sig was left behind.

    153b3 is the CONTROL and shares this fixture, so it stays in the same function: without it the narrowing above is indistinguishable from disabling the check. Its item is ADDED AND TICKED in one go, deliberately. An item merely added is ALSO an open-items violation, and with only one rotating check surfaced per stop the hook showed that one instead: the first draft asserted on a
    message the rotation had chosen not to print. Ticking leaves exactly one rotating violation, so what the stop surfaces is unambiguous.
    """
    wl.brief_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.plant_state(wlfix.STATE_BODY)
    age_file(wl.state_file(), 30)
    wl.check("allow", "", "153b2 SETUP: the document is adopted and its signature banked")

    # A DIFFERENT session adds its own item. Peer bookkeeping, not this session's world.
    # THE BASH ASSERTION HERE COULD NOT FAIL (12-agent-docs-and-focus.sh:143). `reqcli --add cafe1234 ...` ran under this session's own id, and since v19 the identity check refuses that outright with an identity mismatch, so NO peer item was ever planted and the stop below observed a world nothing had touched.
    # The write goes through the peer's own identity instead, which is what the case means by a DIFFERENT session adding its own item, and is the only shape that can still fire if the ownership scoping regresses.
    wl.cli_as("cafe1234", "--add", "cafe1234", "peer item nobody else owns")
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.check("allow", "", "153b2: a peer's item does NOT stale my recovery document")

    mine = added_id(wl.cli("--add", "deadbeef", "my own item, which IS a reason to rewrite"))
    wl.cli("--tick", "deadbeef", mine, "landed, suite green, exit 0")
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    got = wl.run()
    assert "STATE.md is stale" in got.out, (
        "153b3: the ownership scope swallowed a REAL staleness: %s" % got.out[:400]
    )


def test_153c_a_detached_head_enforces_and_the_branch_cannot_change_the_verdict(wl):  # noqa: F811
    """T9, INVERTED 2026-08-18, and the inversion is the point. This case used to assert the opposite, that no resolvable branch made the STATE.md check REPORT-ONLY (operator decision 2026-07-30), because the document's path needed a branch to resolve. HEAD detaches during every interactive rebase and this operator rebase-merges everything, so that exemption meant the one artifact
    designed to survive compaction went unenforced for the whole of a rebase.

    The path is keyed on the SESSION now, so there is nothing to be blind about. The document is deleted first, deliberately: asserting "it did not block" on a healthy tree would pass just as well on a check that had been turned off. A MISSING document with work outstanding must block WITHOUT a branch, and the control runs the identical fixture WITH one and demands the same
    verdict, which is the actual claim, that the branch no longer matters.
    """
    wl.brief_now()
    wl.hand_now()
    wl.state_file().unlink()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")

    branchless = wl.run({"WORKLIST_AGENT_BRANCH": ""})
    assert '"decision": "block"' in branchless.out, branchless.out[:300]
    assert "STATE.md is missing" in branchless.out, branchless.out[:300]
    assert "freshness check is BLIND" not in branchless.out, (
        "T9: the branchless stop named a blindness: %s" % branchless.out[:300]
    )

    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    with_branch = wl.run()
    assert '"decision": "block"' in with_branch.out, with_branch.out[:300]
    assert "STATE.md is missing" in with_branch.out, (
        "T9 CONTROL: the branch changed the verdict: %s" % with_branch.out[:300]
    )


def test_153d_trap_titles_feed_the_judge_and_bodies_and_subheadings_never_do(wl):  # noqa: F811
    """T10/T11: the judge sees `##` titles only; bodies, `###` and absent files are safe."""
    store = wlfix.import_wl("wl_store")
    messages = wlfix.import_wl("worklist_messages")
    docs = wl.proj / "docs" / "agent-reference"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "TRAPS.md").write_text(
        "# Traps\n\n## Real trap title one\n\nsecret body line\n\n### a sub-heading\n\n## Second title\n",
        encoding="utf-8",
    )

    heads = store.trap_headings(str(wl.proj))
    prompt = messages.JUDGE_PROMPT % {
        "streak": 1,
        "remaining": "r",
        "leases": 0,
        "loop": "l",
        "citations": "c",
        "message": "m",
        "traps": "\n".join("  - " + head for head in heads) or "  (none recorded)",
    }
    assert heads == ["Real trap title one", "Second title"], heads
    assert "Real trap title one" in prompt
    assert "secret body line" not in prompt, "the judge prompt carried a trap BODY"
    assert "a sub-heading" not in prompt, "the judge prompt carried a ### sub-heading"
    assert store.trap_headings(str(wl.proj) + "/nonexistent") == [], (
        "an absent file did not read as empty"
    )


def test_153f_the_live_traps_file_is_not_silently_truncated(wl):  # noqa: F811
    """WHY A LIVE-FILE CASE AND NOT ONLY FIXTURES. The old cap was the literal 40 and TRAPS.md reached exactly 40 on 2026-08-23, one entry from invisibility, with no warning anywhere: the list simply ended and the judge saw a corpus that looked complete.

    A fixture case cannot notice that, because a fixture never grows. This one compares the parser against the REAL file and reds the day the corpus outgrows the cap.
    """
    store = wlfix.import_wl("wl_store")
    repo_root = wlfix.STOP_DIR.parents[2]
    cap = store.TRAP_HEADING_CAP
    live = store.trap_headings(str(repo_root))
    on_disk = len(
        [
            line
            for line in (repo_root / "docs/agent-reference/TRAPS.md")
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()
            if line.startswith("## ") and not line.startswith("### ")
        ]
    )

    # THE ALARM. Equality alone would pass VACUOUSLY on a moved or renamed TRAPS.md (0 == 0), so the floor is asserted separately.
    assert len(live) == on_disk, "live parses %d headings against %d on disk" % (len(live), on_disk)
    assert on_disk >= 42, "the live file is not empty (%d >= 42)" % on_disk
    assert on_disk <= cap, "the live file is under the cap (%d <= %d)" % (on_disk, cap)
    assert not any("further entries" in head for head in live), "the live list carries a sentinel"

    # ABOVE the cap: exactly one synthetic element, naming the count dropped.
    over = wl.base / "capfix-over" / "docs" / "agent-reference"
    over.mkdir(parents=True, exist_ok=True)
    (over / "TRAPS.md").write_text(
        "".join("## heading %d\n\nbody\n\n" % index for index in range(cap + 5)), encoding="utf-8"
    )
    got_over = store.trap_headings(str(over.parents[1]))
    assert len(got_over) == cap + 1, "over-cap length is %d" % len(got_over)
    assert got_over, got_over[-1:]
    assert "+5 further entries" in got_over[-1], got_over[-1:]

    # THE CONTROL. Exactly AT the cap must be indistinguishable from under it: no sentinel, no truncation, nothing appended. Without this the sentinel arm passes just as happily with an off-by-one that tags every list ever built.
    at = wl.base / "capfix-at" / "docs" / "agent-reference"
    at.mkdir(parents=True, exist_ok=True)
    (at / "TRAPS.md").write_text(
        "".join("## heading %d\n\nbody\n\n" % index for index in range(cap)), encoding="utf-8"
    )
    got_at = store.trap_headings(str(at.parents[1]))
    assert len(got_at) == cap, "CONTROL: at-cap length is %d" % len(got_at)
    assert not any("further entries" in head for head in got_at), "CONTROL: at-cap grew a sentinel"


def test_154_next_wakeups_is_gone_from_both_emit_paths(wl):  # noqa: F811
    """Operator, 2026-08-04: "we don't need to print next wakeup times. We should just track the hook moments and notify/warn when needed. let's go for efficient ai context usage". The section printed every task's next firing on every full stop.

    154b shares this fixture and follows in sequence, because the FOCUS=off dump-all block carried the section too and must not any more.
    """
    wl.brief_now()
    wl.hand_now()
    wl.crons = CRONS_WITH_PROMPTS
    # A real item, so this stop has a guide to print: without one the whole report would be silent (v18) and the absence assertion below would pass vacuously.
    wl.add_item("- [?] (deadbeef) keep the flag? DEFAULT: keep it")
    wl.say(
        "answer\n\n## Remaining\n- #7 thing (pending)\n- the flag decision, deferred with a default"
    )
    wl.task(7, "pending", "thing")

    got = wl.run()
    assert "NEXT WAKEUPS" not in got.out, (
        "154a: the wakeup display survived on allow: %s" % got.out[:260]
    )
    assert "HOURLY LOOP fixture" not in got.out, got.out[:260]
    # CONTROL that 154a is not vacuous: the stop DID produce its normal report, so the absence above is the section being gone rather than the hook being mute.
    assert "WORKLIST GUIDE" in got.out, (
        "154a CONTROL: the stop emitted nothing at all: %s" % got.out[:260]
    )
    assert "keep the flag?" in got.out, got.out[:260]

    wl.age_state("deadbeef", 20)
    wl.task(8, "pending", "moved")
    wl.add_item("- [x] (deadbeef) a finished piece of work")
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)\n- #8 moved (pending)")
    blocked = wl.run({"WORKLIST_FOCUS": "off"})
    assert '"decision": "block"' in blocked.out, blocked.out[:220]
    assert "NEXT WAKEUPS" not in blocked.out, (
        "154b: the wakeup section survived on the dump-all block: %s" % blocked.out[:220]
    )


def test_154c_an_unparseable_schedule_is_still_named(wl):  # noqa: F811
    """THE SURVIVING WARNING. An unparseable schedule is invisible to every other cron check, so deleting the display must not delete this."""
    wl.brief_now()
    wl.hand_now()
    wl.crons = CRONS_BROKEN
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    got = wl.run()
    assert "CANNOT PARSE" in got.out, (
        "154c: a broken schedule went silent with the section: %s" % got.out[:260]
    )
    assert "BROKEN fixture." in got.out, got.out[:260]


def test_154c_control_valid_schedules_raise_no_warning(wl):  # noqa: F811
    """CONTROL: with every schedule valid the warning is silent, so it reports a real defect rather than firing on any cron list at all."""
    wl.brief_now()
    wl.hand_now()
    wl.crons = CRONS_VALID
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    got = wl.run()
    assert "CANNOT PARSE" not in got.out, (
        "154c CONTROL: the warning fired on a healthy cron list: %s" % got.out[:260]
    )


def test_155_supervised_must_correlate_to_the_live_worker_not_just_be_fresh(wl):  # noqa: F811
    """Real review finding (PR #546, comment 3686791985): the freshest `[>]` item across ALL in-flight records was taken as proof of supervision, with no check that it names the SAME worker as the one in live_bg.

    Two leases: one tracking bw1 (the actual watched job) gone STALE past the threshold, one tracking an UNRELATED worker zz9 kept FRESH. The unrelated fresh one must NOT excuse the stale one, which is exactly the forgotten-watch case this exemption exists to exclude.
    """
    wl.env["WORKLIST_STUCK_ROUNDS"] = "1"
    wl.brief_now()
    wl.hand_now()
    stale = stamp(100)
    fresh = stamp()
    until = stamp(-30, "%Y-%m-%dT%H:%MZ")
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "bbbb0001",
            "at": stale,
            "by": "deadbeef",
            "s": " ",
            "o": "deadbeef",
            "t": "watching the real job",
        },
    )
    plant_event(
        wl,
        {
            "ev": "lease",
            "id": "bbbb0001",
            "at": stale,
            "by": "deadbeef",
            "until": until,
            "worker": "bw1",
        },
    )
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "bbbb0002",
            "at": fresh,
            "by": "deadbeef",
            "s": " ",
            "o": "deadbeef",
            "t": "unrelated, still being renewed",
        },
    )
    plant_event(
        wl,
        {
            "ev": "lease",
            "id": "bbbb0002",
            "at": fresh,
            "by": "deadbeef",
            "until": until,
            "worker": "zz9",
        },
    )
    wl.bg = json.dumps(
        [
            {
                "id": "bw1",
                "type": "shell",
                "status": "running",
                "description": "the actual watched job",
            }
        ]
    )
    wl.task(9, "pending", "thing")
    wl.say("answer\n\n## Remaining\n- #9 thing (pending), watched via bw1 and zz9")

    last = None
    for _ in range(3):
        last = wl.run()
    assert "EMPLOY A PLANNING OR INVESTIGATION AGENT" in last.out, (
        "155: the unrelated fresh lease wrongly silenced the exempt-overrun: %s" % last.out[:220]
    )


def test_155b_control_the_correlated_lease_being_fresh_does_supervise(wl):  # noqa: F811
    """CONTROL: a fresh lease correlated to the live worker DOES supervise."""
    wl.env["WORKLIST_STUCK_ROUNDS"] = "1"
    wl.brief_now()
    wl.hand_now()
    fresh = stamp()
    until = stamp(-30, "%Y-%m-%dT%H:%MZ")
    plant_event(
        wl,
        {
            "ev": "add",
            "id": "bbbb0003",
            "at": fresh,
            "by": "deadbeef",
            "s": " ",
            "o": "deadbeef",
            "t": "watching the real job",
        },
    )
    plant_event(
        wl,
        {
            "ev": "lease",
            "id": "bbbb0003",
            "at": fresh,
            "by": "deadbeef",
            "until": until,
            "worker": "bw1",
        },
    )
    wl.bg = json.dumps(
        [
            {
                "id": "bw1",
                "type": "shell",
                "status": "running",
                "description": "the actual watched job",
            }
        ]
    )
    wl.task(9, "pending", "thing")
    wl.say("answer\n\n## Remaining\n- #9 thing (pending), watched via bw1")

    last = None
    for _ in range(3):
        last = wl.run()
    assert "EMPLOY A PLANNING OR INVESTIGATION AGENT" not in last.out, (
        "155b: a genuinely fresh, correlated lease still fired: %s" % last.out[:220]
    )


def test_156_focus_surfaces_one_rotating_check_per_stop_in_lru_order(wl):  # noqa: F811
    """v13 FOCUS. Two rotating checks outstanding (an open item and a stale brief). Stop 1 surfaces exactly one; stop 2 surfaces the OTHER; stop 3 cycles back. The header counts what is held back, so nothing is silently forgotten."""
    wl.hand_now()
    wl.env["WORKLIST_STUCK_ROUNDS"] = "99"
    wl.add_item("- [ ] (deadbeef) open thing")
    # The message carries NO '## Remaining' section, which is the second rotating violation (the session-brief check that used to fill this role was deleted 2026-09-24), so exactly TWO rotating checks are outstanding and the cycle length is 2.
    wl.say("answer")
    first = wl.run().out
    wl.newturn()
    wl.say("answer")
    second = wlfix.quoted(wl.run().out)
    wl.newturn()
    wl.say("answer")
    third = wlfix.quoted(wl.run().out)

    # QUOTED, not named: since 2026-09-24 the check this stop did not quote is NAMED below the quote, so both texts appear and only the quoted region tells which one rotated in.
    one_open = "OPEN worklist item" in wlfix.quoted(first)
    one_brief = "no '## Remaining' section" in wlfix.quoted(first)
    two_open = "OPEN worklist item" in second
    two_brief = "no '## Remaining' section" in second
    assert one_open != one_brief, "156: stop 1 surfaced %d rotating checks" % (one_open + one_brief)
    assert two_open != two_brief, "156: stop 2 surfaced %d rotating checks" % (two_open + two_brief)
    assert one_open != two_open, "156: the two stops surfaced the same check"
    assert "check(s) outstanding, surfacing" in first, first[:300]
    assert "more check(s) outstanding" in first, first[:300]
    assert ("OPEN worklist item" in third) == one_open, "156b: rotation did not cycle back (LRU)"


def test_156c_control_focus_off_restores_the_dump_all_block(wl):  # noqa: F811
    """The revert control for the whole feature: the same two-check fixture shows BOTH bodies in one block when focus is off."""
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) open thing")
    wl.say("answer")
    got = wl.run({"WORKLIST_FOCUS": "off"})
    assert "OPEN worklist item" in got.out, got.out[:300]
    assert "no '## Remaining' section" in got.out, got.out[:300]
    assert "check(s) failed" in got.out, got.out[:300]


def test_156d_the_always_tier_rides_every_focused_block(wl):  # noqa: F811
    """CI-red is latched (its block budget is spent at compute time), so hiding it behind rotation would swallow it forever. It must appear IN ADDITION to the one rotating check."""
    ci_setup(wl)
    ci_rollup(wl, "FAILURE", "[%s]" % ci_job("Quality / Static", "FAILURE"))
    wl.add_item("- [ ] (deadbeef) open thing")
    got = ci_run(wl)
    assert '"decision": "block"' in got.out, got.out[:400]
    assert "CI IS RED ON PR" in got.out, got.out[:400]
    assert "OPEN worklist item" in got.out, (
        "156d: the rotating check is missing from the focused block: %s" % got.out[:400]
    )
