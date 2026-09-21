"""Ported from `.claude/hooks/stop/worklist-cases/25-first-touch.sh`.

The onboarding notice, and above all when it stays QUIET.

WHY. The Stop hook already tells a session what to do, but only once it tries to stop, after the work. A fresh or post-compaction session learns the rules by hitting that wall: it finishes a job, writes `## Remaining` from memory, and gets refused. The operator's words were that such sessions "hit the wall and repeat the same mistakes like completing the job without updating the
remainings by invoking stop hook's commands with specific arguments".

WHAT IS ACTUALLY AT RISK is not the notice firing, it is the notice firing too often. Measured on the transcript corpus: 38 of 41 sessions never edited a file and used 6 to 39 tool calls each. An unconditional first-tool-call notice would have fired on all 38 with nothing to say, and a notice that is noise 38 times out of 41 is one nobody reads on the other three. So most of the
tests below assert SILENCE, and the emitting ones exist mainly to prove the silence is a choice rather than a permanently broken hook.
"""

from __future__ import annotations

import json
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


def test_25_onboard_py_is_where_the_suite_expects_it():
    """The bash failed the whole group loudly when the script was missing rather than skipping it, because a silent skip is how a test file stops covering anything."""
    assert ONBOARD.is_file(), "onboard.py missing at %s" % ONBOARD


def test_25_an_unarmed_session_is_silent(wl, ft):  # noqa: F811
    assert combined(ftrun(wl, ft, EV_BASH)) == "", "it spoke without ever being armed"


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
