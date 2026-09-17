"""`rediacc_ci.ci.assert_channel_for_event` against its bash twin.

The twin takes argv and nothing else: no subprocess, no file, no network, no env beyond the colour decision. So both sides are driven DIRECTLY with the same arguments under the same tiny environment, and stdout, stderr and the exit code are compared byte-for-byte. There are no recording fakes here because there is nothing to fake -- inventing one would prove a stub works, not that
the port does.

TWO NORMALISATIONS, BOTH NARROW AND BOTH STATED:

  * `$0` is the program's own name, so the usage line necessarily names the
    `.sh` on one side and the `.py` on the other. `usage_tail` strips exactly
    that one token and the rest is compared literally.
  * NOTHING ELSE. Every other case asserts raw equality of both streams.

The K=5 ledger is `.ci/shadow/w7p6-assert-channel-for-event.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-assert-channel-for-event --assert --k 5`).
"""

from __future__ import annotations

import re
import shlex

from rediacc_ci.ci import assert_channel_for_event as port
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/ci/assert-channel-for-event.sh"
MODULE = "rediacc_ci.ci.assert_channel_for_event"


def run_both(
    *args: str, tty: str | None = None, env_extra: dict[str, str] | None = None
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    quoted = " ".join(shlex.quote(a) for a in args)
    extra = env_extra or {}
    old_env = diff.env_for(**extra)
    new_env = diff.env_for(**extra, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s %s" % (TWIN, quoted), env=old_env, tty=tty, timeout=30)
    new = diff.bash_streams("python3 -m %s %s" % (MODULE, quoted), env=new_env, tty=tty, timeout=30)
    return old, new


def assert_identical(*args: str, expect_exit: int) -> tuple[int, str, str]:
    old, new = run_both(*args)
    assert old[0] == expect_exit, "twin exit changed: %r" % (old,)
    assert new[0] == old[0]
    assert new[1] == old[1]
    assert new[2] == old[2]
    return old


def test_schedule_with_an_empty_channel_passes() -> None:
    old = assert_identical("schedule", "", expect_exit=0)
    assert old[2] == "✓ Channel '<empty>' matches event 'schedule'\n"
    assert old[1] == ""


def test_schedule_with_any_channel_is_the_orphan_r2_guard() -> None:
    old = assert_identical("schedule", "dryrun-abc123", expect_exit=1)
    assert old[2] == (
        "✗ Channel must be empty for schedule events (got: dryrun-abc123).\n"
        "✗   schedule must not produce R2 uploads.\n"
    )


def test_workflow_dispatch_with_any_channel_fails_with_the_rehearsal_wording() -> None:
    old = assert_identical("workflow_dispatch", "edge", expect_exit=1)
    assert "The nightly rehearsal must not produce R2 uploads." in old[2]


def test_workflow_dispatch_empty_passes() -> None:
    assert_identical("workflow_dispatch", "", expect_exit=0)


def test_push_must_be_edge() -> None:
    assert_identical("push", "edge", expect_exit=0)
    old = assert_identical("push", "stable", expect_exit=1)
    assert "push events must resolve to edge channel (got: 'stable')." in old[2]


def test_push_with_an_empty_channel_fails() -> None:
    assert_identical("push", "", expect_exit=1)


def test_pull_request_must_be_pr_n() -> None:
    assert_identical("pull_request", "pr-42", expect_exit=0)
    assert_identical("pull_request", "pr-0", expect_exit=0)


def test_pull_request_rejects_near_misses() -> None:
    for channel in ("pr-", "pr-4x", "PR-4", "xpr-4", "pr-4 ", "pr--4", "edge", ""):
        assert_identical("pull_request", channel, expect_exit=1)


def test_the_pr_anchor_is_end_of_string_not_end_of_line() -> None:
    """`pr-1\\n` must fail on BOTH sides.

    This is the one place a naive Python port diverges silently: bash's `$` in
    `[[ =~ ^pr-[0-9]+$ ]]` anchors at end of STRING, while Python's `$` also
    matches before a trailing newline, so `re.match(r"pr-[0-9]+$", "pr-1\\n")` succeeds where bash refuses. `fullmatch` is what closes it.
    """
    assert_identical("pull_request", "pr-1\n", expect_exit=1)


def test_unknown_event_warns_and_accepts_anything() -> None:
    """The twin's `*)` arm fails OPEN. Pinned, not fixed: see the port's header."""
    old = assert_identical("pull_request_target", "dryrun-abc", expect_exit=0)
    assert old[2] == (
        "⚠ Unknown event: pull_request_target (channel: 'dryrun-abc'); "
        "accepting without assertion\n"
        "✓ Channel 'dryrun-abc' matches event 'pull_request_target'\n"
    )


def test_a_capitalised_event_name_is_unknown_and_therefore_unguarded() -> None:
    """`Push` is not `push`. A workflow typo defeats the guard on both sides."""
    assert_identical("Push", "dryrun-abc", expect_exit=0)


def test_missing_channel_argument_is_the_empty_channel() -> None:
    """`${2-}` on an absent second argument, not an error."""
    assert_identical("schedule", expect_exit=0)


def test_extra_arguments_are_ignored_by_both() -> None:
    assert_identical("push", "edge", "junk", "more", expect_exit=0)


def test_no_arguments_prints_usage_and_exits_2() -> None:
    old, new = run_both()
    assert old[0] == 2
    assert new[0] == 2
    assert old[1] == ""
    assert new[1] == ""
    assert usage_tail(old[2]) == " <event_name> <channel>\n"
    assert usage_tail(new[2]) == usage_tail(old[2])
    assert old[2].startswith("✗ Usage: ")
    assert new[2].startswith("✗ Usage: ")


def test_an_empty_event_name_is_also_usage() -> None:
    old, new = run_both("", "edge")
    assert (old[0], new[0]) == (2, 2)
    assert usage_tail(new[2]) == usage_tail(old[2])


def usage_tail(stderr: str) -> str:
    """Everything after the `$0` token, which is the only legitimate difference."""
    prefix, _, tail = stderr.partition("Usage: ")
    assert prefix == "✗ ", "not a usage line: %r" % stderr
    _, _, rest = tail.partition(" ")
    return " " + rest


def twin_text() -> str:
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        return fh.read()


def test_the_case_arms_still_match_the_twins() -> None:
    """A NEW arm in the twin must break this port, not slip past it.

    The port turns the twin's `case` into a dict plus two branches, which is a COPY of a control-flow table. Re-read the twin rather than restating it: a sixth event arm added there is a rule the port would silently not have.
    """
    text = twin_text()
    arms = re.findall(r"^    ([a-z_*|]+)\)$", text, re.MULTILINE)
    assert arms == ["schedule", "push", "pull_request", "workflow_dispatch", "*"]
    assert set(port.EMPTY_CHANNEL_EVENTS) == {"schedule", "workflow_dispatch"}
    for advice in port.EMPTY_CHANNEL_EVENTS.values():
        assert 'log_error "%s"' % advice in text


def test_the_pr_pattern_is_the_twins_pattern() -> None:
    assert port.PR_CHANNEL.pattern == "pr-[0-9]+"
    assert "^%s$" % port.PR_CHANNEL.pattern in twin_text()


def test_colour_on_a_terminal_is_byte_identical() -> None:
    """The failing path with stderr on a pty: escapes included, not stripped."""
    old, new = run_both("schedule", "dryrun-abc", tty="stderr")
    assert old[0] == new[0] == 1
    assert diff.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert new[2] == old[2]


def test_no_color_suppresses_colour_on_both_sides_on_a_terminal() -> None:
    old, new = run_both("schedule", "x", tty="stderr", env_extra={"NO_COLOR": "1"})
    assert diff.escape_bytes(old[2]) == 0
    assert new[2] == old[2]


def test_the_echo_e_divergence_is_pinned_not_repaired() -> None:
    """common.sh logs with `echo -e`; this module formats the message as data.

    A channel containing a literal backslash-t makes the twin emit a TAB and the port emit two characters. `log.py` states the decision ("A SECOND DIVERGENCE, and this one is a bug being dropped rather than a decision"), so the assertion here is that they DISAGREE, in exactly this way and nowhere else. If a future reader "fixes" the port to match, this test says what they have
    re-imported.
    """
    old, new = run_both("schedule", "dryrun-a\\tb")
    assert old[0] == new[0] == 1
    assert "dryrun-a\tb" in old[2], "bash stopped interpreting escapes: %r" % old[2]
    assert "dryrun-a\\tb" in new[2]
    assert new[2] != old[2]
