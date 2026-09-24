"""Ported from `.claude/hooks/stop/worklist-cases/25-first-touch.sh`.

The onboarding notice, and above all when it stays QUIET.

WHY. The Stop hook already tells a session what to do, but only once it tries to stop, after the work. A fresh or post-compaction session learns the rules by hitting that wall: it finishes a job, writes `## Remaining` from memory, and gets refused. The operator's words were that such sessions "hit the wall and repeat the same mistakes like completing the job without updating the
remainings by invoking stop hook's commands with specific arguments".

WHAT IS ACTUALLY AT RISK is not the notice firing, it is the notice firing too often. Measured on the transcript corpus: 38 of 41 sessions never edited a file and used 6 to 39 tool calls each. An unconditional first-tool-call notice would have fired on all 38 with nothing to say, and a notice that is noise 38 times out of 41 is one nobody reads on the other three. So most of the
tests below assert SILENCE, and the emitting ones exist mainly to prove the silence is a choice rather than a permanently broken hook.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
import subprocess
import sys

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

ONBOARD = wlfix.STOP_DIR.parent / "context" / "onboard.py"

FT_SID = "ffffeeee-1111-2222-3333-444444444444"
OTHER_SID = "aaaabbbb-9999-8888-7777-666666666666"

EV_BASH = {"session_id": FT_SID, "tool_name": "Bash"}
EV_EDIT = {"session_id": FT_SID, "tool_name": "Edit"}
EV_SUB = {"session_id": FT_SID, "tool_name": "Bash", "parent_tool_use_id": "toolu_x"}


@pytest.fixture
def ft(wl):  # noqa: F811
    """The first-touch state directory, rebuilt per test as the bash rebuilt it per arm.

    UNDER THE SANDBOX ROOT, as the bash put it under `$BASE`: the onboarding hook resolves the worklist from the same TMPDIR the fixture pins, so a state directory outside it would read one session's marker against another's store.
    """
    state = wl.base / "firsttouch"
    state.mkdir(parents=True, exist_ok=True)
    return state


def ftrun(fix, state, event: dict, *argv: str, session: str = FT_SID, extra: dict | None = None):
    """One PostToolUse invocation, THE EVENT ON STDIN.

    NO empty stdin here, and that is not an oversight. A PostToolUse hook reads its event FROM STDIN, so handing it nothing means it sees no tool_name, correctly concludes this is not an Edit, and stays silent, which looks exactly like arm (b) being broken. That cost one debugging round in the bash original.
    """
    env = dict(fix.env)
    env.update(
        {
            "CTX_BAND_STATE_DIR": str(state),
            "CLAUDE_CODE_SESSION_ID": session,
            "WORKLIST_SESSION_ID": session,
            "CLAUDE_PROJECT_DIR": str(fix.proj),
            "TMPDIR": str(fix.base / "tmp"),
        }
    )
    if extra:
        env.update(extra)
    proc = subprocess.run(
        [sys.executable, str(ONBOARD), *argv],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return wlfix.Result(proc.stdout, proc.stderr, proc.returncode)


def combined(result: wlfix.Result) -> str:
    return result.out + result.err


def ftadd(fix, text: str, session: str = FT_SID) -> str:
    """One OPEN item owned by the first-touch session, returning its id.

    RAISES rather than returning empty when the CLI refuses, because arm (a) is the branch that only exists when the session owns something: a silently-refused `--add` would leave the session owning nothing, the hook would take arm (b)'s path, and the case would assert silence and pass while testing the wrong arm entirely.
    """
    env = dict(fix.env)
    env["WORKLIST_SESSION_ID"] = session
    got = fix.python(["--add", session[:8], text], env=env)
    found = re.search(r"#([0-9a-f]{8})", got.out)
    if got.rc != 0 or not found:
        raise AssertionError(
            "FIXTURE BROKEN: --add %s was refused (rc=%d): %s"
            % (session[:8], got.rc, (got.out + got.err)[:200])
        )
    return found.group(1)


def bump_epoch(state, epoch: int, session: str = FT_SID) -> None:
    """Move the BAND state's epoch counter without firing any hook.

    This is the compaction nothing else in the tree sees. `band-notice.py`'s usage-drop backstop is the only thing that notices an in-place compaction, and all it does is move this counter: SessionStart and PostCompact never fire, so `--arm` is never called. Writing the counter directly is exactly what that backstop leaves behind, and the marker's own epoch mismatch is the only
    remaining evidence a compaction happened.
    """
    path = state / ("%s.json" % session[:8])
    path.write_text(json.dumps({"epoch": epoch, "band": -1}), encoding="utf-8")


def marker_of(state, session: str = FT_SID) -> dict:
    return json.loads((state / ("%s-onboard.json" % session[:8])).read_text(encoding="utf-8"))


def test_25_onboard_py_is_where_the_suite_expects_it():
    """The bash failed the whole group loudly when the script was missing rather than skipping it, because a silent skip is how a test file stops covering anything."""
    assert ONBOARD.is_file(), "onboard.py missing at %s" % ONBOARD


def test_25_an_unarmed_session_is_silent(wl, ft):  # noqa: F811
    assert combined(ftrun(wl, ft, EV_BASH)) == "", "it spoke without ever being armed"


def test_25_arm_a_fires_at_the_first_tool_call_carrying_the_id_and_the_prefix(wl, ft):  # noqa: F811
    """Arm (a): the session OWNS something, so it is told at tool call #1 and not again.

    THREE CLAIMS, and the case fails if any one of them slips. It fires on a BASH call, which is what separates arm (a) from arm (b) rather than a matter of timing. It carries the ITEM ID, because a bare count of one open item sends the session straight back to the store to ask which one. And the verb prefix is THIS session's, pre-substituted: the operator's phrase was "commands
    with specific arguments", the identity check refuses a wrong `<me>`, and a notice handing over an id that cannot be used has spent its one emission teaching an error.
    """
    item = ftadd(wl, "arm (a) subject line")
    ftrun(wl, ft, EV_BASH, "--arm")

    out = combined(ftrun(wl, ft, EV_BASH))
    assert "already owns 1 open worklist item" in out, "arm (a) never fired: %s" % out[:200]
    assert item in out, "the notice named a count but not the id #%s: %s" % (item, out[:300])
    for verb in ("--tick ffffeeee", "--update ffffeeee", "--defer ffffeeee"):
        assert verb in out, "%s was not pre-substituted: %s" % (verb, out[:300])
    # The prefix came from the SESSION, not from the ambient fixture identity. Without this the assertions above pass on a notice that hands every session `deadbeef`, which the identity check would refuse on first use.
    assert wlfix.ME not in out, "it substituted the ambient prefix %s: %s" % (wlfix.ME, out[:300])

    assert combined(ftrun(wl, ft, EV_BASH)) == "", "it repeated on the next call in one epoch"
    assert marker_of(ft)["state"] == "delivered", "the marker never recorded the delivery"


def test_25_arm_b_five_non_edit_tool_calls_with_nothing_owned_emit_nothing(wl, ft):  # noqa: F811
    """This is the arm that would have nagged 38 of 41 real sessions."""
    ftrun(wl, ft, EV_BASH, "--arm")
    for call in range(1, 6):
        out = combined(ftrun(wl, ft, EV_BASH))
        assert out == "", "nagged on non-edit tool call #%d: %s" % (call, out[:120])
    # And the state machine actually moved, rather than the hook being inert.
    marker = ft / "ffffeeee-onboard.json"
    text = marker.read_text(encoding="utf-8") if marker.is_file() else ""
    assert '"await-edit"' in text, (
        "the marker never advanced, so the silence is a no-op rather than a decision: %s"
        % text.replace("\n", "")[:120]
    )


def test_25_arm_b_fires_on_the_first_edit_once(wl, ft):  # noqa: F811
    ftrun(wl, ft, EV_BASH, "--arm")
    for _ in range(5):
        ftrun(wl, ft, EV_BASH)
    out = combined(ftrun(wl, ft, EV_EDIT))
    assert "owns 0 worklist items" in out, "no notice on the first edit: %s" % out[:160]
    assert "--tick ffffeeee" in out, "the prefix was not pre-substituted: %s" % out[:160]
    assert combined(ftrun(wl, ft, EV_EDIT)) == "", "it repeated within one epoch"


def test_25_an_epoch_bump_re_arms_and_the_same_sequence_without_one_stays_silent(wl, ft):  # noqa: F811
    """The compaction that fires NO hook, and its control.

    An in-place compaction can fire neither SessionStart nor PostCompact, so `--arm` is never called and the marker still reads `delivered` from before the context was replaced. The session on the other side of it has forgotten the store completely and is the single case this whole notice was asked for. The only trace left is the epoch counter that `band-notice.py`'s usage-drop
    backstop moved, so the marker re-arms on the MISMATCH.

    THE CONTROL IS THE HALF THAT CAN ROT. An assertion that a bumped epoch speaks again passes just as well on a hook that speaks on every single call, which is the 38-of-41 nag this design exists to avoid. So the same tool call is driven three times WITHOUT a bump first, and silence is required each time before the bump is allowed to break it.
    """
    item = ftadd(wl, "an item that outlives the context")
    ftrun(wl, ft, EV_BASH, "--arm")
    assert item in combined(ftrun(wl, ft, EV_BASH)), "arm (a) never fired, so nothing is re-armed"
    assert marker_of(ft)["epoch"] == 0, "the delivery recorded no epoch to mismatch against"

    for call in range(1, 4):
        out = combined(ftrun(wl, ft, EV_BASH))
        assert out == "", "spoke again at call #%d with the epoch unmoved: %s" % (call, out[:160])

    bump_epoch(ft, 1)
    again = combined(ftrun(wl, ft, EV_BASH))
    assert "already owns 1 open worklist item" in again, (
        "an epoch the marker has never seen left it silent, which is the post-compaction session it exists for: %s"
        % again[:200]
    )
    assert item in again, "the re-armed notice dropped the id: %s" % again[:200]
    assert combined(ftrun(wl, ft, EV_BASH)) == "", "once per EPOCH, not once per call after one"
    assert marker_of(ft)["epoch"] == 1, "the marker did not adopt the epoch it re-armed on"


def test_25_a_subagent_call_is_silent(wl, ft):  # noqa: F811
    """A subagent is never told about the store."""
    ftrun(wl, ft, EV_BASH, "--arm")
    assert combined(ftrun(wl, ft, EV_SUB)) == "", "it spoke to a subagent"


def test_25_cannot_say_is_not_zero(wl, ft):  # noqa: F811
    """This one was a real bug.

    `worklist.py --list --open <me>` exits 1 for an EMPTY slice, so keying on the exit code alone collapsed "owns nothing" into "cannot say" and arm (b) could never fire. The converse matters more: a store that REFUSES to answer (an identity mismatch) must produce silence, never the confident notice that nothing is owned.
    """
    ftrun(wl, ft, EV_EDIT, "--arm", session=OTHER_SID)
    out = combined(ftrun(wl, ft, EV_EDIT, session=OTHER_SID))
    assert out == "", "it asserted an empty slice the store never confirmed: %s" % out[:140]


def test_25_the_off_switch_silences_it(wl, ft):  # noqa: F811
    ftrun(wl, ft, EV_BASH, "--arm")
    out = combined(ftrun(wl, ft, EV_EDIT, extra={"ONBOARD_NOTICE": "off"}))
    assert out == "", "ONBOARD_NOTICE=off did not silence it: %s" % out[:120]


def test_25_safety_it_must_never_break_a_tool_call(wl, ft):  # noqa: F811
    """A PostToolUse hook that exits non-zero, or writes garbage to stdout, breaks the call it is attached to. Both are asserted against a deliberately corrupt marker."""
    (ft / "ffffeeee-onboard.json").write_text("not json at all", encoding="utf-8")
    got = ftrun(wl, ft, EV_EDIT)
    assert got.rc == 0, "exited %d on a corrupt marker; that breaks the tool call" % got.rc
    out = combined(got)
    if out:
        try:
            json.loads(out)
        except ValueError:
            raise AssertionError("wrote non-JSON to stdout: %s" % out[:120]) from None


# ---- `--audit`, the measurement (plan section 5) ----------------------------
#
# WHY THESE CASES CARRY A FULL FIXTURE INSTEAD OF RUNNING THE REAL TREE. The audit's answer depends on three artifacts nobody controls from a test (175 transcripts, a shared event log and a compaction floor that moves), and an assertion written against today's numbers would be red tomorrow for reasons that say nothing about the code.
# So the cohort is BUILT: two sessions whose verdicts are known by construction and one that must be skipped.

AUDIT_BASE = "2026-09-10T00:00:00Z"


def at(minutes: float) -> str:
    """AUDIT_BASE plus `minutes`, in the seconds-and-Z spelling the event log uses."""
    when = dt.datetime.fromisoformat(AUDIT_BASE) + dt.timedelta(minutes=minutes)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def rec_start(stamp):
    return {"type": "user", "message": {"content": "go"}, "timestamp": stamp}


def rec_tool(stamp, name="Bash"):
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "id": "tu_1", "name": name, "input": {}}]},
        "timestamp": stamp,
    }


def rec_notice(stamp):
    """A DELIVERED notice, in the shape the harness really writes.

    The text is taken from the hook's own arm (b) wording rather than invented, because the audit finds a delivery by grepping for marks that must still appear in that wording. A case that planted its own sentence would go green on an audit that could no longer see a real delivery.
    """
    return {
        "type": "attachment",
        "attachment": {
            "type": "hook_additional_context",
            "content": ["This session owns 0 worklist items, and a file has just been edited."],
        },
        "timestamp": stamp,
    }


def rec_refusal(stamp):
    return {
        "type": "user",
        "isMeta": True,
        "message": {"content": "Stop hook feedback:\nDo not stop yet.\n\nsomething is open"},
        "timestamp": stamp,
    }


def mk_transcript(where, sid, records):
    path = where / ("%s.jsonl" % sid)
    with path.open("w", encoding="utf-8") as handle:
        # Two untimed records first, exactly as a real transcript opens. They are what makes the "first timestamped record" rule a rule rather than "line one".
        handle.write(json.dumps({"type": "ai-title", "aiTitle": "t", "sessionId": sid}) + "\n")
        handle.write(json.dumps({"type": "mode", "mode": "normal", "sessionId": sid}) + "\n")
        for rec in records:
            handle.write(json.dumps(rec) + "\n")
    return path


def mk_events(fix, rows):
    """Plant store events directly, one line per (by, at).

    WRITTEN RATHER THAN DRIVEN THROUGH THE CLI on purpose: `--add` stamps the wall clock, and every verdict here is a comparison between a transcript stamp and a store stamp. A fixture that could not place a write BEFORE a refusal could not test the direction that matters.
    """
    path = fix.store_dir / "audit-fixture.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for index, (by, stamp) in enumerate(rows):
            handle.write(
                json.dumps(
                    {"ev": "add", "id": "ev%06d" % index, "at": stamp, "by": by, "o": by, "t": "x"}
                )
                + "\n"
            )
    return path


REFUSED_SID = "aaaa1111-0000-0000-0000-000000000000"
WROTE_SID = "bbbb2222-0000-0000-0000-000000000000"
PREFLOOR_SID = "cccc3333-0000-0000-0000-000000000000"
CARRYOVER_SID = "eeee5555-0000-0000-0000-000000000000"


@pytest.fixture
def cohort(wl):  # noqa: F811
    """Four transcripts and a store, with every stamp chosen so the verdicts are known in advance.

    REFUSED_SID is refused at +5 and does not write until +20: refused-before-write. WROTE_SID writes at +2 and is refused at +8: the same shape in the other order, and the case exists because an audit that hard-coded YES would pass every assertion about the first session. PREFLOOR_SID starts an hour before the log begins, which is the session a compaction has made unmeasurable.
    CARRYOVER_SID opens with a refusal REPLAYED from the conversation it continues, which is a real shape found on the live corpus rather than an invented one.
    """
    where = wl.base / "transcripts"
    where.mkdir(parents=True, exist_ok=True)
    mk_transcript(
        where,
        REFUSED_SID,
        [rec_start(at(10)), rec_tool(at(10.1)), rec_notice(at(11)), rec_refusal(at(15))],
    )
    mk_transcript(
        where,
        WROTE_SID,
        [
            rec_start(at(10)),
            rec_tool(at(10.1)),
            rec_tool(at(10.5), "Edit"),
            rec_notice(at(11)),
            rec_refusal(at(18)),
        ],
    )
    mk_transcript(where, PREFLOOR_SID, [rec_start(at(-60)), rec_tool(at(-59)), rec_refusal(at(-50))])
    # A RESUMED SESSION, in the shape f4da5c2e really has on disk: a new transcript that opens at +10 and whose next records are REPLAYED from the context it continues, stamps and all. Its only refusal happened at +3, two contexts ago, and belongs to neither this session's clock nor its conduct.
    mk_transcript(
        where,
        CARRYOVER_SID,
        [rec_start(at(10)), rec_refusal(at(3)), rec_tool(at(10.1))],
    )
    # The floor is the log's OWN first entry, so it is pinned by an event from a writer that is not in the cohort; without it the floor would be whichever fixture session happened to write first.
    mk_events(
        wl,
        [
            ("dddd4444", at(0)),
            (WROTE_SID[:8], at(12)),
            (REFUSED_SID[:8], at(30)),
            (CARRYOVER_SID[:8], at(40)),
        ],
    )
    return where


def arun(fix, state, where, *argv):
    """`onboard.py --audit ...` against the fixture corpus, stdin closed."""
    env = dict(fix.env)
    env.update(
        {
            "CTX_BAND_STATE_DIR": str(state),
            "CLAUDE_PROJECT_DIR": str(fix.proj),
            "TMPDIR": str(fix.base / "tmp"),
            "WORKLIST_PROJECTS_DIR": str(where),
        }
    )
    proc = subprocess.run(
        [sys.executable, str(ONBOARD), "--audit", *argv],
        input="",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return wlfix.Result(proc.stdout, proc.stderr, proc.returncode)


def row_of(payload: dict, sid8: str) -> dict:
    for row in payload["sessions"]:
        if row["sid"] == sid8:
            return row
    raise AssertionError("no row for %s in %s" % (sid8, [r["sid"] for r in payload["sessions"]]))


def test_25_audit_reports_refusal_before_write_in_both_directions(wl, ft, cohort):  # noqa: F811
    """The headline metric, and the case is worth only as much as its second half.

    A verdict that is always YES satisfies every assertion about the refused session; a verdict that is always NO satisfies every assertion about the one that wrote first. Only the pair pins it, and the two transcripts differ in nothing except the ORDER of the refusal and the write.
    """
    got = arun(wl, ft, cohort, "--json")
    assert got.rc == 0, "the audit failed on a cohort built to be measurable: %s" % got.err[:300]
    payload = json.loads(got.out)

    refused = row_of(payload, REFUSED_SID[:8])
    assert refused["refused_before_write"] is True, (
        "a refusal at +5 with no write until +20 was not counted: %s" % refused
    )
    assert refused["refusal_min"] == pytest.approx(5.0, abs=0.2)
    assert refused["write_min"] == pytest.approx(20.0, abs=0.2)

    wrote = row_of(payload, WROTE_SID[:8])
    assert wrote["refused_before_write"] is False, (
        "a session that wrote at +2 and was refused at +8 was counted as refused first: %s" % wrote
    )
    assert wrote["ever_wrote"] is True
    assert wrote["write_min"] == pytest.approx(2.0, abs=0.2)

    assert payload["summary"]["refused_before_write"] == 1
    assert payload["summary"]["audited"] == 3


def test_25_audit_does_not_charge_a_session_with_a_refusal_it_inherited(wl, ft, cohort):  # noqa: F811
    """A resumed transcript replays the previous context's records, and one of them is a refusal.

    FOUND BY RUNNING THE TOOL RATHER THAN BY READING IT. On the live corpus f4da5c2e reported its first refusal at MINUS 2.0 minutes: the file opens at 12:05:08 and its fourth record is a `Stop hook feedback` stamped 12:03:10, replayed from the conversation it continues. A refusal before the session began is not this session's, and counting it made a session that was refused at
    +56 look refused before it had started. Anything stamped earlier than the first record is carry-over, counted so the drop stays visible and never charged to the session.
    """
    payload = json.loads(arun(wl, ft, cohort, "--json").out)
    row = row_of(payload, CARRYOVER_SID[:8])
    assert row["carryover"] == 1, "the replayed record was not recognised as carry-over: %s" % row
    assert row["refusal_min"] is None, (
        "an inherited refusal was charged to the session at %s minutes" % row["refusal_min"]
    )
    assert row["refused_before_write"] is False, (
        "a session whose only refusal predates its own transcript was counted as refused first: %s"
        % row
    )


def test_25_audit_skips_a_session_the_compaction_floor_has_made_unmeasurable(wl, ft, cohort):  # noqa: F811
    """A session older than the log is UNKNOWN, and unknown is never folded in as clean.

    `worklist.py --compact` re-stamps every historical event `by: "compact"`, so a session that ran before the surviving log cannot be shown to have written. Counted, it would read as "never wrote" and inflate the headline on evidence that no longer exists; dropped silently, it would shrink the denominator with nobody told. It is skipped BY NAME instead.
    """
    payload = json.loads(arun(wl, ft, cohort, "--json").out)
    assert sorted(r["sid"] for r in payload["sessions"]) == sorted(
        [REFUSED_SID[:8], WROTE_SID[:8], CARRYOVER_SID[:8]]
    ), "the pre-floor session was audited anyway: %s" % [r["sid"] for r in payload["sessions"]]
    skips = dict(tuple(pair) for pair in payload["shape"]["skips"])
    assert PREFLOOR_SID[:8] in skips, "it was dropped without being reported: %s" % skips
    assert "floor" in skips[PREFLOOR_SID[:8]], skips[PREFLOOR_SID[:8]]

    plain = arun(wl, ft, cohort)
    assert PREFLOOR_SID[:8] in plain.out, "the human report hid the skip: %s" % plain.out[-400:]
    assert "3 audited" in plain.out, plain.out[:200]
    assert "1 skipped" in plain.out, plain.out[:200]


def test_25_audit_refuses_an_empty_cohort_rather_than_reporting_a_clean_one(wl, ft, cohort):  # noqa: F811
    """Zero inputs is a FAILURE. Three ways to see nothing, and each exits non-zero saying which.

    This is the only way an audit can lie: a report over no sessions is perfectly clean and perfectly meaningless, and it is indistinguishable from a good result unless the tool refuses to print one.
    """
    empty = wl.base / "no-transcripts"
    empty.mkdir(parents=True, exist_ok=True)
    got = arun(wl, ft, empty)
    assert got.rc != 0, "an empty transcript directory exited 0: %s" % got.out[:300]
    assert "ZERO transcripts" in got.err, got.err[:300]

    for path in wl.store_dir.glob("*.jsonl"):
        path.unlink()
    got = arun(wl, ft, cohort)
    assert got.rc != 0, "an empty event log exited 0: %s" % got.out[:300]
    assert "ZERO events" in got.err, got.err[:300]

    # And the floor rule taken to its limit: every session older than the log leaves nothing to audit, which must read as "cannot say", never as "all clear".
    mk_events(wl, [("dddd4444", at(600))])
    got = arun(wl, ft, cohort)
    assert got.rc != 0, "a cohort emptied by the floor exited 0: %s" % got.out[:300]
    assert "were skipped" in got.err, got.err[:300]


def test_25_audit_refuses_to_run_when_the_notice_wording_outruns_its_marks():
    """The control on the control.

    The audit finds a delivery by grepping the transcript for marks copied from the notice text. Reword the notice without touching NOTICE_MARKS and every delivery becomes invisible: the silence rate goes to 100%, the delivery latency empties out, and the report reads as a notice nobody ever needed.
    That failure is green, so the live text is checked against the marks before any transcript is opened.
    """
    spec = importlib.util.spec_from_file_location("onboard_under_test", ONBOARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.notice_marks_hold(), "the live notice text carries none of its own marks"
    mod.text_owns = lambda *_unused: "a rewording that mentions nothing recognisable"
    assert not mod.notice_marks_hold(), (
        "a notice rewritten past every mark was accepted, so a 100% silence rate would be reported as a measurement"
    )
