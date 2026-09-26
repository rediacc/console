"""`rediacc_ci.ci.assert_channel_for_event`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/ci/assert-channel-for-event.sh` and the port over the same argv under the same tiny environment and compared exit code, stdout and stderr. The K=5 ledger `.ci/shadow/w7p6-assert-channel-for-event.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted and every case that
executed it compares against `goldens/assert-channel-for-event/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

NOTHING IS FAKED, because there is nothing to fake: the twin took argv and nothing else -- no subprocess, no file, no network, no environment beyond the colour decision. Inventing a stub would prove the stub works, not that the port does.

ONE NORMALISATION, AND IT IS THE SAME ONE THE DIFFERENTIAL APPLIED. `$0` is the program's own name, so the usage line necessarily names the `.sh` in the recording and the `.py` in the port's output. `mask_prog` replaces exactly that token and the rest of every stream is compared byte-for-byte.

THE TWO STALENESS ALARMS THAT PARSED THE TWIN'S SOURCE ARE GONE, and the recordings replace them. One re-read the twin's `case` arms so a sixth event could not appear there without breaking the port's dict; the other re-read `^pr-[0-9]+$`. A deleted file does not grow a sixth arm. What could still drift is the port's copy, so
`test_every_event_arm_is_answered_by_a_recording` and `test_the_pr_boundary_cases_are_all_recorded` re-derive both tables from the RECORDED bytes rather than restating them.
"""

from __future__ import annotations

import re
import shlex
import typing

import pytest

from rediacc_ci.ci import assert_channel_for_event as port
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

SLUG = "assert-channel-for-event"
MODULE = "rediacc_ci.ci.assert_channel_for_event"

# `✗ Usage: <prog> <event_name> <channel>`: the one token a `.sh` child and a `.py` one disagree on.
_PROG = re.compile(r"(?<=Usage: )\S+")

# name -> (argv, how the run is wired)
CASE_KW: dict[str, tuple[tuple[str, ...], dict[str, typing.Any]]] = {
    "schedule-with-an-empty-channel": (("schedule", ""), {}),
    "schedule-with-a-channel": (("schedule", "dryrun-abc123"), {}),
    "workflow-dispatch-with-a-channel": (("workflow_dispatch", "edge"), {}),
    "workflow-dispatch-with-an-empty-channel": (("workflow_dispatch", ""), {}),
    "push-to-edge": (("push", "edge"), {}),
    "push-to-stable": (("push", "stable"), {}),
    "push-with-an-empty-channel": (("push", ""), {}),
    "pull-request-pr-42": (("pull_request", "pr-42"), {}),
    "pull-request-pr-0": (("pull_request", "pr-0"), {}),
    "pull-request-a-bare-prefix": (("pull_request", "pr-"), {}),
    "pull-request-a-non-digit-suffix": (("pull_request", "pr-4x"), {}),
    "pull-request-an-uppercase-prefix": (("pull_request", "PR-4"), {}),
    "pull-request-a-leading-character": (("pull_request", "xpr-4"), {}),
    "pull-request-a-trailing-space": (("pull_request", "pr-4 "), {}),
    "pull-request-a-doubled-hyphen": (("pull_request", "pr--4"), {}),
    "pull-request-the-edge-channel": (("pull_request", "edge"), {}),
    "pull-request-an-empty-channel": (("pull_request", ""), {}),
    "pull-request-a-trailing-newline": (("pull_request", "pr-1\n"), {}),
    "an-unknown-event": (("pull_request_target", "dryrun-abc"), {}),
    "a-capitalised-event-name": (("Push", "dryrun-abc"), {}),
    "a-missing-channel-argument": (("schedule",), {}),
    "extra-arguments": (("push", "edge", "junk", "more"), {}),
    "no-arguments": ((), {}),
    "an-empty-event-name": (("", "edge"), {}),
    "colour-on-a-terminal": (("schedule", "dryrun-abc"), {"tty": "stderr"}),
    "no-color-on-a-terminal": (
        ("schedule", "x"),
        {"tty": "stderr", "env_extra": {"NO_COLOR": "1"}},
    ),
    "an-escape-in-the-channel": (("schedule", "dryrun-a\\tb"), {}),
}

CASES = tuple(CASE_KW)

# The one case the port does not reproduce byte for byte, on purpose. Compared by shape, in its own test.
DIVERGENT = "an-escape-in-the-channel"


def mask_prog(text: str) -> str:
    return _PROG.sub("<prog>", text)


def run(
    name: str,
    command: str,
    *,
    tty: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """One side, once, over this case's argv."""
    args = CASE_KW[name][0]
    quoted = " ".join(shlex.quote(arg) for arg in args)
    extra = dict(env_extra or {})
    if command.startswith("python3"):
        extra["PYTHONPATH"] = ".ci"
        extra["PYTHONDONTWRITEBYTECODE"] = "1"
    return diff.bash_streams(
        "%s %s" % (command, quoted), env=diff.env_for(**extra), tty=tty, timeout=30
    )


def render(returncode: int, stdout: str, stderr: str) -> str:
    return frozen.render(returncode, mask_prog(stdout), mask_prog(stderr))


def recorded(name: str) -> tuple[int, str, str]:
    """One golden's recorded exit code and two streams."""
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def drive(name: str, *, module: str = MODULE) -> tuple[int, str, str]:
    returncode, stdout, stderr = run(name, "python3 -m %s" % module, **CASE_KW[name][1])
    return returncode, mask_prog(stdout), mask_prog(stderr)


def compare(name: str) -> tuple[int, str, str]:
    want = recorded(name)
    got = drive(name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged from the recorded bytes" % name
    assert got[2] == want[2], "%s: stderr diverged from the recorded bytes" % name
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c != DIVERGENT])
def test_port_matches_the_twins_recorded_output(name: str) -> None:
    compare(name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_schedule_with_an_empty_channel_passes() -> None:
    returncode, stdout, stderr = recorded("schedule-with-an-empty-channel")
    assert returncode == 0
    assert stdout == ""
    assert stderr == "✓ Channel '<empty>' matches event 'schedule'\n"


def test_schedule_with_any_channel_is_the_orphan_r2_guard() -> None:
    returncode, _, stderr = recorded("schedule-with-a-channel")
    assert returncode == 1
    assert stderr == (
        "✗ Channel must be empty for schedule events (got: dryrun-abc123).\n"
        "✗   schedule must not produce R2 uploads.\n"
    )


def test_workflow_dispatch_with_any_channel_fails_with_the_rehearsal_wording() -> None:
    returncode, _, stderr = recorded("workflow-dispatch-with-a-channel")
    assert returncode == 1
    assert "The nightly rehearsal must not produce R2 uploads." in stderr


def test_workflow_dispatch_empty_passes() -> None:
    assert recorded("workflow-dispatch-with-an-empty-channel")[0] == 0


def test_push_must_be_edge() -> None:
    assert recorded("push-to-edge")[0] == 0
    returncode, _, stderr = recorded("push-to-stable")
    assert returncode == 1
    assert "push events must resolve to edge channel (got: 'stable')." in stderr
    assert recorded("push-with-an-empty-channel")[0] == 1


def test_the_pr_boundary_cases_are_all_recorded() -> None:
    """The twin's `^pr-[0-9]+$` re-derived from the recordings instead of restated.

    Two shapes pass and eight near misses fail, and the port's own pattern is asked to agree with every one of them. A port that widened the pattern would still match the two green recordings; it is the eight red ones that close it.
    """
    passing = {"pull-request-pr-42", "pull-request-pr-0"}
    for name in CASES:
        if not name.startswith("pull-request-"):
            continue
        channel = CASE_KW[name][0][1]
        returncode = recorded(name)[0]
        assert returncode == (0 if name in passing else 1), name
        assert bool(port.PR_CHANNEL.fullmatch(channel)) == (returncode == 0), name


def test_the_pr_anchor_is_end_of_string_not_end_of_line() -> None:
    """`pr-1\\n` was refused by the twin and must be refused here.

    The one place a naive Python port diverges silently: bash's `$` in `[[ =~ ^pr-[0-9]+$ ]]` anchors at end of STRING, while Python's `$` also matches before a trailing newline, so `re.match(r"pr-[0-9]+$", "pr-1\\n")` succeeds where bash refused. `fullmatch` is what closes it.
    """
    assert recorded("pull-request-a-trailing-newline")[0] == 1
    assert port.PR_CHANNEL.match("pr-1\n") is not None, "the divergence this pins is gone"
    assert port.PR_CHANNEL.fullmatch("pr-1\n") is None


def test_unknown_event_warns_and_accepts_anything() -> None:
    """The twin's `*)` arm failed OPEN. Recorded, not repaired: see the port's header."""
    returncode, _, stderr = recorded("an-unknown-event")
    assert returncode == 0
    assert stderr == (
        "⚠ Unknown event: pull_request_target (channel: 'dryrun-abc'); "
        "accepting without assertion\n"
        "✓ Channel 'dryrun-abc' matches event 'pull_request_target'\n"
    )


def test_a_capitalised_event_name_is_unknown_and_therefore_unguarded() -> None:
    """`Push` is not `push`. A workflow typo defeated the guard in the twin too."""
    assert recorded("a-capitalised-event-name")[0] == 0


def test_missing_channel_argument_is_the_empty_channel() -> None:
    """`${2-}` on an absent second argument, not an error."""
    assert recorded("a-missing-channel-argument")[0] == 0


def test_extra_arguments_are_ignored() -> None:
    assert recorded("extra-arguments")[0] == 0


def test_no_arguments_prints_usage_and_exits_2() -> None:
    returncode, stdout, stderr = recorded("no-arguments")
    assert returncode == 2
    assert stdout == ""
    assert stderr == "✗ Usage: <prog> <event_name> <channel>\n"


def test_an_empty_event_name_is_also_usage() -> None:
    returncode, _, stderr = recorded("an-empty-event-name")
    assert returncode == 2
    assert stderr == "✗ Usage: <prog> <event_name> <channel>\n"


def test_every_event_arm_is_answered_by_a_recording() -> None:
    """The twin's `case` table, re-derived from the recorded bytes.

    Four named arms plus the `*)` fallthrough, and the port's `EMPTY_CHANNEL_EVENTS` advice lines are read back out of the recordings rather than restated here. An advice line edited in the port and nowhere else stops matching the bytes the twin wrote.
    """
    assert set(port.EMPTY_CHANNEL_EVENTS) == {"schedule", "workflow_dispatch"}
    for event, advice in port.EMPTY_CHANNEL_EVENTS.items():
        name = "%s-with-a-channel" % event.replace("_", "-")
        assert "✗ %s\n" % advice in recorded(name)[2], event
    assert "push events must resolve to edge channel" in recorded("push-to-stable")[2]
    assert (
        "pull_request events must resolve to pr-N channel"
        in recorded("pull-request-the-edge-channel")[2]
    )
    assert "Unknown event:" in recorded("an-unknown-event")[2]


# --------------------------------------------------------------------------- Colour and the one recorded divergence ---------------------------------------------------------------------------


def test_colour_on_a_terminal_is_byte_identical() -> None:
    """The failing path with stderr on a pty: escapes included, not stripped."""
    returncode, _, stderr = recorded("colour-on-a-terminal")
    assert returncode == 1
    assert diff.escape_bytes(stderr) > 0, "the twin printed no colour on a tty"
    compare("colour-on-a-terminal")


def test_no_color_suppresses_colour_on_a_terminal() -> None:
    assert diff.escape_bytes(recorded("no-color-on-a-terminal")[2]) == 0
    compare("no-color-on-a-terminal")


def test_the_echo_e_divergence_is_pinned_not_repaired() -> None:
    """common.sh logged with `echo -e`; this module formats the message as data.

    A channel containing a literal backslash-t made the twin emit a TAB and makes the port emit two characters. `log.py` states the decision ("A SECOND DIVERGENCE, and this one is a bug being dropped rather than a decision"), so the assertion here is that the recording and the port DISAGREE, in exactly this way and nowhere else. If a future reader "fixes" the port to match,
    this test says what they have re-imported.
    """
    want_exit, _, want_err = recorded(DIVERGENT)
    returncode, _, stderr = drive(DIVERGENT)
    assert want_exit == returncode == 1
    assert "dryrun-a\tb" in want_err, "the twin stopped interpreting escapes: %r" % want_err
    assert "dryrun-a\\tb" in stderr
    assert stderr != want_err


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_end_of_line_anchor_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Swap `fullmatch` for `match`.

    That is the exact spelling a reader reaches for when translating `[[ =~ ^pr-[0-9]+$ ]]`, and it accepts `pr-1\\n` -- a channel name carrying a newline, which is what a mis-quoted workflow expression produces. The recorded verdict for `pull-request-a-trailing-newline` is 1; the mutant returns 0 and prints the green line instead. The mutation runs from a throwaway copy of
    the package's module file; the tracked port is never touched.
    """
    source = port.__file__
    with open(source, encoding="utf-8") as fh:
        original = fh.read()
    anchor = "if not PR_CHANNEL.fullmatch(channel):\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, "if not PR_CHANNEL.match(channel):\n")

    mutant_dir = tmp_path / "mutant"
    mutant_dir.mkdir(parents=True, exist_ok=True)
    mutant = mutant_dir / "assert_channel_for_event.py"
    mutant.write_text(mutated, encoding="utf-8")

    name = "pull-request-a-trailing-newline"
    returncode, _, stderr = run(name, "python3 %s" % mutant, **CASE_KW[name][1])
    want_exit, _, want_err = recorded(name)
    assert want_exit == 1, "the recorded verdict for a trailing newline moved"
    assert returncode == 0, "the plant did not change the verdict"
    assert stderr != want_err, "the plant is invisible on stderr"

    compare(name)
    with open(source, encoding="utf-8") as fh:
        assert fh.read() == original
