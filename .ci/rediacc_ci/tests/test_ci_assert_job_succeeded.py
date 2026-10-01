"""`rediacc_ci.ci.assert_job_succeeded` against its bash twin's frozen answers.

The twin, `.ci/scripts/ci/assert-job-succeeded.sh`, is deleted (PLAN-retire-bash-oracles B3); `differential.twin_streams` answers its side from `goldens/twins/ci.assert-job-succeeded.jsonl`. Re-record with `PYTHONPATH=.ci python3 -m rediacc_ci.tests.regolden <twin> --source port --reason "<why>"`.

argv in, two streams and an exit code out; no subprocess, no file, no env beyond the colour decision, so both sides are driven directly and compared byte-for-byte. The only normalisation is the `$0` token in the usage line, which is the program's own name and therefore necessarily differs; `usage_tail` strips exactly that and nothing else.

The K=5 ledger is `.ci/shadow/w7p6-assert-job-succeeded.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-assert-job-succeeded --assert --k 5`).
"""

from __future__ import annotations

import shlex

from rediacc_ci import paths
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/ci/assert-job-succeeded.sh"
MODULE = "rediacc_ci.ci.assert_job_succeeded"


def run_both(
    *args: str, tty: str | None = None, env_extra: dict[str, str] | None = None
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    quoted = " ".join(shlex.quote(a) for a in args)
    extra = env_extra or {}
    old_env = diff.env_for(**extra)
    new_env = diff.env_for(**extra, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    new = diff.bash_streams("python3 -m %s %s" % (MODULE, quoted), env=new_env, tty=tty, timeout=30)
    old = diff.twin_streams(
        TWIN, "bash %s %s" % (TWIN, quoted), env=old_env, tty=tty, timeout=30, port=lambda: new
    )
    return old, new


def assert_identical(*args: str, expect_exit: int) -> tuple[int, str, str]:
    old, new = run_both(*args)
    assert old[0] == expect_exit, "twin exit changed: %r" % (old,)
    assert new[0] == old[0]
    assert new[1] == old[1]
    assert new[2] == old[2]
    return old


def usage_tail(stderr: str) -> str:
    prefix, _, tail = stderr.partition("Usage: ")
    assert prefix == "✗ ", "not a usage line: %r" % stderr
    _, _, rest = tail.partition(" ")
    return " " + rest


def test_success_passes_and_says_so() -> None:
    old = assert_identical("housekeeping", "success", expect_exit=0)
    assert old[2] == "✓ housekeeping result: success\n"
    assert old[1] == ""


def test_skipped_is_the_transitive_skip_signature_and_fails() -> None:
    old = assert_identical("housekeeping", "skipped", expect_exit=1)
    assert old[2] == (
        "✓ housekeeping result: skipped\n"
        "✗ housekeeping was skipped. This is the GHA transitive-skip propagation bug "
        "(finding J).\n"
        "✗   Some job in housekeeping's needs chain skipped and GH Actions propagated\n"
        "✗   the skip through to housekeeping. Prefix the if: on the housekeeping job\n"
        "✗   with 'always() &&' so skips in its needs chain cannot silently disable it.\n"
        "✗   The static audit .ci/scripts/security/check-workflow-gates.sh should also\n"
        "✗   have caught this; investigate why it did not.\n"
    )


def test_cancelled_and_failure_are_accepted_with_a_warning() -> None:
    for result in ("cancelled", "failure"):
        old = assert_identical("finalize-release-sentinel", result, expect_exit=0)
        assert (
            old[2]
            .splitlines()[1]
            .startswith(
                "⚠ finalize-release-sentinel result=%s; treating as externally-imposed" % result
            )
        )
        assert "no need to pile on." in old[2]


def test_an_unknown_result_fails_closed() -> None:
    """The opposite choice from assert_channel_for_event's `*)` arm, on purpose."""
    old = assert_identical("housekeeping", "neutral", expect_exit=1)
    assert (
        "✗ housekeeping has unexpected result='neutral' "
        "(not success/skipped/cancelled/failure).\n" in old[2]
    )
    assert (
        "✗   Update .ci/rediacc_ci/ci/assert_job_succeeded.py to handle this state explicitly.\n"
        in old[2]
    )


def test_the_advice_names_a_file_that_exists() -> None:
    """Rule T, failing on the bash behaviour: the retired twin's advice named itself, a file that no longer exists. The intentional golden delta is on the unknown- and empty-result records."""
    old, new = run_both("housekeeping", "neutral")
    advice = [line for line in new[2].splitlines() if "Update " in line]
    assert advice, new[2]
    target = advice[0].split("Update ", 1)[1].split(" ", 1)[0]
    assert (paths.repo_root() / target).is_file(), (
        "the advice names %s, which does not exist" % target
    )
    assert new == old


def test_an_empty_result_fails_closed_too() -> None:
    """`${{ needs.<job>.result }}` yields '' when the job name is misspelled."""
    old = assert_identical("housekeeping", "", expect_exit=1)
    assert "unexpected result=''" in old[2]


def test_a_missing_second_argument_is_the_same_as_an_empty_one() -> None:
    assert_identical("housekeeping", expect_exit=1)


def test_the_label_is_interpolated_into_every_advice_line() -> None:
    """Five occurrences in the skipped arm, TWO of them on one line.

    Counted rather than eyeballed: the `Prefix the if: on the <label> job` line names the label twice, and a port that interpolated only the first occurrence would still pass every substring assertion above.
    """
    old = assert_identical("some-other-job", "skipped", expect_exit=1)
    assert old[2].count("some-other-job") == 5
    warn, _ = run_both("some-other-job", "failure")
    assert warn[2].count("some-other-job") == 3


def test_case_matters_in_the_result() -> None:
    for result in ("Success", "SKIPPED", "success "):
        assert_identical("housekeeping", result, expect_exit=1)


def test_extra_arguments_are_ignored_by_both() -> None:
    assert_identical("housekeeping", "success", "junk", expect_exit=0)


def test_no_arguments_prints_usage_and_exits_2() -> None:
    old, new = run_both()
    assert old[0] == 2
    assert new[0] == 2
    assert old[1] == ""
    assert new[1] == ""
    assert usage_tail(old[2]) == " <job_label> <result>\n"
    assert usage_tail(new[2]) == usage_tail(old[2])


def test_an_empty_label_is_also_usage() -> None:
    old, new = run_both("", "success")
    assert (old[0], new[0]) == (2, 2)
    assert usage_tail(new[2]) == usage_tail(old[2])


def test_colour_on_a_terminal_is_byte_identical() -> None:
    old, new = run_both("housekeeping", "skipped", tty="stderr")
    assert old[0] == new[0] == 1
    assert diff.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert new[2] == old[2]


def test_the_warn_arm_is_also_byte_identical_on_a_terminal() -> None:
    """A different glyph and colour (⚠ / bright yellow) from the error arm."""
    old, new = run_both("housekeeping", "cancelled", tty="stderr")
    assert old[0] == new[0] == 0
    assert diff.escape_bytes(old[2]) > 0
    assert new[2] == old[2]


def test_no_color_suppresses_colour_on_both_sides_on_a_terminal() -> None:
    old, new = run_both("housekeeping", "skipped", tty="stderr", env_extra={"NO_COLOR": "1"})
    assert diff.escape_bytes(old[2]) == 0
    assert new[2] == old[2]
