"""The base battery, ported from `.claude/hooks/stop/worklist-cases/01-core-blocking.sh`.

Open items, `[?]` deferrals, session briefs, `## Remaining`, the PostCompact handback, cron shape, and STATE.md size and aim. One test per numbered bash case, with the same assertions against the same subprocess.

THE CONTROLS ARE THE POINT of several of these, and they are marked as such: a shape verdict that printed an age, a peers block that appeared with no peers, a waitled rule that rejected a legitimate next action. Each is a document that must still PASS, so the rule under test cannot be satisfied by refusing everything.
"""

from __future__ import annotations

import json
import threading

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

PEER_BODY = """Session cafe1234 owns packages/cli/src/services/licensing and the two drill scripts under scripts/dev, all of them uncommitted. A git add -A from any other session in this checkout would sweep them into somebody else s commit, which is the cross-session fact that has no home in a per-session file.

## Next action
Finish the renewal drill and report the soft-claim slot count."""


def test_01_an_open_item_blocks(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) do the thing")
    wl.check("block", "OPEN worklist item", "an open [ ] item blocks")


def test_02_a_deferral_with_no_default_blocks(wl):  # noqa: F811
    wl.say("here is my answer\n\n## Remaining\nnothing")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [?] (deadbeef) should we do X")
    wl.check("block", "no DEFAULT:", "a deferral with no DEFAULT: blocks")


def test_03_a_deferral_with_a_default_does_not_block(wl):  # noqa: F811
    wl.say("answer\n\n## Remaining\n- the X decision")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [?] (deadbeef) should we do X DEFAULT: do X on Monday")
    wl.check("allow", "operator may answer", "a deferral WITH DEFAULT: does not block")


def test_04_a_missing_session_brief_blocks(wl):  # noqa: F811
    wl.say("answer\n\n## Remaining\n- stuff")
    wl.add_item("- [?] (deadbeef) q DEFAULT: d")
    wl.check("block", "session brief is missing", "a missing brief blocks")


def test_05_a_stale_session_brief_blocks(wl):  # noqa: F811
    wl.say("answer\n\n## Remaining\n- stuff")
    wl.add_item("- [?] (deadbeef) q DEFAULT: d")
    wl.brief_at(wlfix.ME, 200)
    wl.check("block", "session brief is stale", "a stale brief blocks")


def test_06_a_pending_task_with_no_remaining_section_blocks(wl):  # noqa: F811
    wl.say("All done, nothing to report.")
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "merge the chain")
    wl.check("block", "no '## Remaining' section", "pending task + no ## Remaining blocks")


def test_07_the_same_pending_task_with_a_remaining_section_passes(wl):  # noqa: F811
    wl.say("Here is the answer.\n\n## Remaining\n| #7 | merge the chain | pending, you |")
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "merge the chain")
    wl.check("allow", "", "pending task + ## Remaining allowed (judge off)")


def test_08_completed_tasks_are_not_remaining_work(wl):  # noqa: F811
    wl.say("All done.")
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "completed", "merge the chain")
    wl.check("allow", "", "a completed task does not demand a Remaining section")


def test_09_focus_off_puts_every_violation_in_one_block(wl):  # noqa: F811
    """v13 made the FOCUSED single-check block the default; the dump-all contract survives behind WORKLIST_FOCUS=off and this case keeps that path exercised."""
    wl.say("nothing")
    wl.add_item("- [ ] (deadbeef) open thing")
    wl.add_item("- [?] (deadbeef) undefaulted q")
    out = wl.run({"WORKLIST_FOCUS": "off"}).out
    assert "check(s) failed" in out, out[:400]
    violations = json.loads(out)["reason"].count("\n\n  ")
    assert violations >= 3, "expected >=3 violations in one block, got %d" % violations


def test_10_the_recursion_guard_exits_silently(wl):  # noqa: F811
    """GITHUB_ACTIONS is pinned for a reason specific to THIS case: it asserts EMPTY output, and the hook's CI no-op also produces empty output. Inheriting a true value in Actions would make it pass whether or not the recursion guard exists at all."""
    wl.add_item("- [ ] (deadbeef) open thing")
    event = json.dumps(
        {"session_id": wl.sid, "cwd": str(wl.proj), "transcript_path": str(wl.transcript)}
    )
    got = wl.run({"STOPHOOK_CHILD": "1"}, event=event)
    assert not (got.out + got.err).strip(), "guard produced output: %s" % (got.out + got.err)[:200]


def test_11_an_unreachable_judge_fails_closed(wl):  # noqa: F811
    """A live cron in the event, else the idle check fires statically and the stop never reaches the judge path this case exists to pin."""
    wl.say("waiting on CI.\n\n## Remaining\n- #7 merge the chain (pending)")
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "merge the chain")
    wl.judge_mode = "on"
    event = json.dumps(
        {
            "session_id": wl.sid,
            "cwd": str(wl.proj),
            "transcript_path": str(wl.transcript),
            "session_crons": wlfix.DEFAULT_CRONS,
        }
    )
    got = wl.run({"PATH": str(wl.base / "binonly"), "HOME": str(wl.base / "nohome")}, event=event)
    assert got.decision == "block", "judge failure did not block: %s" % got.out[:300]
    assert "no-escape-hatch" in got.out, got.out[:300]


def test_12_an_empty_world_allows_the_stop(wl):  # noqa: F811
    wl.say("All finished.")
    wl.brief_now()
    wl.hand_now()
    wl.check("allow", "", "an empty world allows the stop")


def test_16_a_remaining_section_that_omits_an_open_task_blocks(wl):  # noqa: F811
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "thing")
    wl.task(8, "pending", "the forgotten one")
    wl.check("block", "OUT OF SYNC", "an omitted task id blocks")


def test_17_naming_every_open_task_passes(wl):  # noqa: F811
    wl.say(
        "answer\n\n## Remaining\n| #7 | thing | pending, me |\n"
        "| #8 | the forgotten one | pending, you |"
    )
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "thing")
    wl.task(8, "pending", "the forgotten one")
    wl.check("allow", "", "all task ids named is fine")


def test_18_a_missing_state_document_blocks_when_work_remains(wl):  # noqa: F811
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.brief_now()
    wl.task(7, "pending", "thing")
    wl.check("block", "STATE.md is missing", "a missing STATE.md blocks")


def test_19_a_thin_state_document_blocks_and_carries_no_age(wl):  # noqa: F811
    """A stub is not a recovery document.

    THE CONTROL: a SHAPE verdict must carry no age at all. `thin` is about the body, and printing a staleness limit beside it suggests that waiting or re-stamping would help. Without the control the change could have simply appended a phrase everywhere and still read as wall-clock.
    """
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.brief_now()
    wl.task(7, "pending", "thing")
    wl.plant_state("wip")
    wl.check("block", "STATE.md is thin", "a too-short STATE.md blocks")
    assert "min old" not in wl.run().out, "a shape verdict printed an age"


def test_20_post_compact_hands_back_state_rules_and_trap_titles(wl):  # noqa: F811
    wl.hand_now()
    (wl.proj / "agent" / wlfix.ME / "RULES.md").write_text(
        "settled fact: the reconciler exists, never rebuild it\n", encoding="utf-8"
    )
    (wl.proj / "docs" / "agent-reference").mkdir(parents=True, exist_ok=True)
    (wl.proj / "docs" / "agent-reference" / "TRAPS.md").write_text(
        "# Traps\n\n## The review tooling comes from main\n\nbody detail here\n", encoding="utf-8"
    )
    out = wl.post_compact({"WORKLIST_AGENT_BRANCH": "agenttest"}).out
    assert "picking up an in-progress session" in out, out[:400]
    assert "ci-overhaul session" in out, out[:400]
    assert "settled fact: the reconciler exists" in out, out[:400]
    assert "The review tooling comes from main" in out, out[:400]
    assert "body detail here" not in out, "PostCompact carried a trap BODY: %s" % out[:400]


def test_21_post_compact_with_no_state_document_still_says_what_to_do(wl):  # noqa: F811
    out = wl.post_compact().out
    assert "NO STATE.md" in out, "missing-STATE.md PostCompact was silent: %s" % out[:300]


def test_21b_post_compact_puts_my_section_first_and_labels_the_peers(wl):  # noqa: F811
    """A compacted session reads top-down, and the block it must act on is its own.

    The peer's section rides along because this checkout runs several sessions at once and a peer's section is the only place the reader learns which uncommitted files are not theirs to sweep. It must be unmistakably marked as not theirs to rewrite, or the briefing itself becomes the next clobber's instruction.
    """
    wl.hand_now()
    wl.state_as("cafe1234", PEER_BODY)
    out = wl.post_compact({"WORKLIST_AGENT_BRANCH": "agenttest"}).out
    own_at = out.find("ci-overhaul session")
    peer_at = out.find("SESSION cafe1234")
    assert own_at >= 0, "ordering wrong (own@%d peer@%d)" % (own_at, peer_at)
    assert peer_at > own_at, "ordering wrong (own@%d peer@%d)" % (own_at, peer_at)
    assert "NOT YOURS" in out, out[:400]
    assert "owns packages/cli" in out, out[:400]


def test_21b_control_a_solo_document_produces_no_peers_block(wl):  # noqa: F811
    """CONTROL: with no peer section there is no peers block at all, so the label is information about the file rather than boilerplate on every briefing."""
    wl.hand_now()
    out = wl.post_compact({"WORKLIST_AGENT_BRANCH": "agenttest"}).out
    assert "ci-overhaul session" in out, out[:400]
    assert "OTHER SESSIONS'" not in out, "a peers block appeared with no peers: %s" % out[:400]


def test_20b_post_compact_with_no_own_section_still_hands_back_the_peers(wl):  # noqa: F811
    """Before sections, this path returned NO state content whatsoever: a compacted session on a branch where only a peer had written was told to reconstruct from what survived, while the peer's section sat unread in the file in front of it. The instruction to write one must survive too, or this becomes a way to inherit a peer's document."""
    wl.state_as("cafe1234", PEER_BODY)
    out = wl.post_compact({"WORKLIST_AGENT_BRANCH": "agenttest"}).out
    assert "NO STATE.md" in out, out[:400]
    assert "owns packages/cli" in out, "the missing branch dropped the peer's section"
    assert "NOT YOURS" in out, out[:400]


def test_22_an_unreadable_transcript_blames_the_hook(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "thing")
    event = json.dumps(
        {
            "session_id": wl.sid,
            "cwd": str(wl.proj),
            "transcript_path": str(wl.base / "does-not-exist.jsonl"),
        }
    )
    out = wl.run(event=event).out
    assert "THIS IS A HOOK BUG" in out, "blind read not distinguished: %s" % out[:300]
    assert '"decision": "block"' in out, out[:300]


def test_23_a_heading_that_lands_late_is_still_honoured(wl):  # noqa: F811
    """The flush race: the retry must pick up a section written mid-check."""
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "thing")
    wl.say("answer with no section yet")
    timer = threading.Timer(0.6, wl.say, ["answer\n\n## Remaining\n- #7 thing (pending)"])
    timer.start()
    try:
        wl.check("allow", "", "a heading written mid-check is picked up by the retry")
    finally:
        timer.join()


def test_24_a_remaining_section_survives_later_narration_blocks(wl):  # noqa: F811
    """THE REGRESSION. Every narration line before a tool call is its own assistant text block, so reading only the LAST block sees a one-liner and calls the section missing. This fired on a real message that did carry its heading."""
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "thing")
    wl.say("Here is the answer.\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.say("Checking one more thing.")
    wl.say("And another.")
    wl.check("allow", "", "a Remaining section survives later narration blocks")


def test_25_two_live_work_crons_block(wl):  # noqa: F811
    """Read from the EVENT, not from a declaration."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.crons = json.dumps(
        [
            {"id": "aaa", "schedule": "*/23 * * * *"},
            {"id": "bbb", "schedule": "17 * * * *"},
            {"id": "p", "schedule": "*/5 * * * *"},
        ]
    )
    wl.check("block", "2 work crons are live", "two live work crons block")


def test_26_the_canonical_cron_shape_does_not_block(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.crons = json.dumps(
        [{"id": "bbb", "schedule": "17 * * * *"}, {"id": "p", "schedule": "*/5 * * * *"}]
    )
    wl.check("allow", "", "work cron + poll cron is fine")


def test_27_an_unconfirmed_operator_block_is_rejected(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, You |")
    wl.task(7, "pending", "thing")
    wl.check("block", "WITHOUT their confirmation", "an unconfirmed operator-block is rejected")


def test_28_the_confirmed_operator_block_is_accepted(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, You (User Thinks So) |")
    wl.task(7, "pending", "thing")
    wl.check("allow", "", "the confirmed operator-block is accepted")


def test_29_a_bloated_state_document_is_rejected(wl):  # noqa: F811
    """It is a prompt, not a report.

    The agent-notes split moved the cap from 1500 to 4000: rules and traps left the budget, so STATE.md needs room for state alone, and 4000 still refuses a pasted transcript. The boundary pair pins the edge, and both bodies carry the '## Next action' section so length is the ONLY variable under test.
    """
    wl.brief_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.plant_state("## Next action\ngo\n" + "x" * 4100 + "\n")
    wl.check("block", "STATE.md is bloated", "an over-long STATE.md blocks")
    wl.plant_state("## Next action\ngo\n" + "x" * 3900 + "\n")
    wl.check("allow", "", "3900-odd chars sits inside the new 4000 budget")


def test_30_a_state_document_without_a_next_action_is_aimless(wl):  # noqa: F811
    """The paragraph guard is DELETED: it was an explicit proxy for the old 600-char cap and split("\\n\\n") counted every markdown heading as a paragraph, which is why the old message had to forbid headings outright. `aimless` is the strictly better gate: presence of a next action IS the value, and padding cannot satisfy it."""
    wl.brief_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.plant_state(
        "You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2, "
        "where the immediate job is to watch the running CI round and diagnose any red from its "
        "complete failed-step log before changing anything at all. Padding padding padding "
        "padding to comfortably clear the thin floor of the shape gate."
    )
    wl.check("block", "STATE.md is aimless", "a STATE.md with no Next action section blocks")
    wl.plant_state(
        "You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2, "
        "where the immediate job is to watch the running CI round and diagnose any red from its "
        "complete failed-step log before changing anything at all.\n\n## Next action\n\n"
        "Diagnose the red from its complete failed-step log, then fix the gate it names."
    )
    wl.check("allow", "", "the same document WITH a Next action section is fine")


def test_30_the_next_action_heading_is_matched_case_insensitively():
    """Probed as a UNIT assertion rather than a third stop: three consecutive stops on an unmoved world trip the stuck detector, which would make this test the wrong gate."""
    store = wlfix.import_wl("wl_store")
    verdict, _ = store.agent_state_shape("x" * 260 + "\n## NEXT ACTION\ngo")
    assert verdict == "ok", "a shouted '## NEXT ACTION' heading was not recognised"


WAITLED_LEADS = (
    "1. Watch `byvmf1xid`; re-check with gh api.",
    "Wait for the run to finish, then review.",
    "- Watch CI run 32259770610",
    "1) Monitor the watch, 2) resume",
    "Keep watching the run.",
    "1. Re-arm the watch on the run.",
    "1. Await green, then review.",
)

WAITLED_CONTROLS = (
    "1. Wire A4 into Navigation.tsx.\n2. Watch CI 322; on green, review.",
    "1. Finish #c84a8a4b, CI is watched by bg byvmf1xid.",
    "1. Read the watchdog classifier verdict and fix the gate.",
    "1. Document the wait semantics in RULES.md.",
)


def shape_of(lead: str) -> str:
    store = wlfix.import_wl("wl_store")
    return store.agent_state_shape("x" * 300 + "\n\n## Next action\n\n" + lead)[0]


def test_v21_waitled_refuses_a_next_action_that_leads_with_a_wait():
    """The root cause of a wave spent watching CI while dozens of open items sat untouched. Every instrument was correctly silent: the no-op wake ladder needs a wake where NOTHING moved, and the session moved something every time. What carried the inversion across compaction was STATE.md itself, whose next action opened with "1. Watch <worker>"."""
    for lead in WAITLED_LEADS:
        assert shape_of(lead) == "waitled", "a wait-led next action was ACCEPTED: %s" % lead


def test_v21_waitled_control_a_work_led_next_action_still_passes():
    """CONTROLS. Each is a document that must still pass, so the rule cannot be satisfied by rejecting everything. The last two matter most: a substring match would reject both, and rejecting a correct document is how a check gets routed around rather than obeyed."""
    for lead in WAITLED_CONTROLS:
        assert shape_of(lead) == "ok", "a legitimate next action was refused: %s" % lead


def test_v22_solo_grind_stays_due_until_shown_then_fires_once_per_episode():
    """Advisory, never blocking. The controls that matter are the SILENT ones: it must not fire twice in an episode, must not fire while a teammate is live, and must re-arm only after the queue actually drains.

    THE STAMP MOVED OUT OF THE FUNCTION (2026-08-28). `solo_grind_due` used to write `solognd` itself, on the stop that COMPUTED it, so a rotation miss or a cadence pause spent the one mention this advisory ever gets on a stop that never rendered a word of it. The stamp is now a DISPLAY-time latch in `run_stop`, so "the text was shown" is modelled here by writing the key by hand.
    """
    checks = wlfix.import_wl("wl_checks")
    seen: dict = {}
    assert checks.solo_grind_due(39, 0, seen) is True, "long queue worked alone must fire"
    assert checks.solo_grind_due(39, 0, seen) is True, "NOT SHOWN yet, so still due"
    seen["solognd"] = 39
    assert checks.solo_grind_due(39, 0, seen) is False, "once per episode, not per stop"
    assert checks.solo_grind_due(39, 2, seen) is False, "silent once a teammate is live"
    assert checks.solo_grind_due(3, 0, seen) is False, "queue drained: the episode ends"
    assert checks.solo_grind_due(20, 0, seen) is True, "and it re-arms when it climbs back"
    assert checks.solo_grind_due(11, 0, {}) is False, "below the floor it never speaks"
    assert checks.solo_grind_due(39, None, {}) is True, "a fact-gatherer that returns None"
    assert checks.solo_grind_due(None, 0, {}) is False, "crashed the whole hook once"
