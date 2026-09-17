"""`rediacc_ci.quality.run_external_gate` against its bash twin.

ALL THREE STATES OF THE FLAG ARE DRIVEN, plus the two the flag can be in by
accident. `hard` and `soft` are the two this wrapper ever legitimately sees --
`skip` is expressed in the step's `if:` and never reaches the script -- so the
cases below cover: hard/pass, hard/fail, soft/pass, soft/fail, UNSET (must be
hard, because a wiring break disabling a blocking gate silently is the failure
this wrapper exists to prevent), EMPTY (same), and an unrecognised value
including the literal `skip` (must refuse, exit 2).

THE EXIT CODE IS THE ASSERTION, not the prose, because the exit code is what
decides red versus green. Three of the cases exist only to pin codes a port can
plausibly get wrong: 127 for a command that is not on PATH, 126 for a file that
is there but not executable, and 143 for a child killed by SIGTERM -- which
`subprocess` reports as `-15` and every shell reports as `128 + 15`. A port
passing the negative number through would turn a killed gate into something
other than a failure.

THREE MESSAGE-TEXT DIVERGENCES ARE EXPECTED AND MASKED RATHER THAN IGNORED, one
per case: the `$0` in the usage line, the spawn-failure wording, and bash's own
`Terminated` job-control notice, which has no Python equivalent. Each masking
site says which divergence it is covering; nothing is compared loosely except
those three.

K=5 LEDGER: `.ci/shadow/w7p6-run-external-gate.observations.jsonl`, recorded
against a disposable scratch git repo built OUTSIDE this checkout (this repo's
working tree is not clean and `shadow-gate.ts --record` refuses a dirty tree).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/quality/run-external-gate.sh"
MODULE = "rediacc_ci.quality.run_external_gate"

_PROGRAM = re.compile(r"EXTERNAL_QUALITY_MODE=hard\|soft \S+ <command\.\.\.>")
# Divergence 3: bash announces a signalled child on its own stderr.
_TERMINATED = re.compile(r"^Terminated\s+.*$\n?", re.MULTILINE)


def _mask(text: str) -> str:
    text = _PROGRAM.sub("EXTERNAL_QUALITY_MODE=hard|soft <prog> <command...>", text)
    return _TERMINATED.sub("", text)


def run_both(
    command: list[str],
    *,
    mode: str | None = None,
    summary_old: pathlib.Path | None = None,
    summary_new: pathlib.Path | None = None,
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    extra: dict[str, str] = {}
    if mode is not None:
        extra["EXTERNAL_QUALITY_MODE"] = mode
    arg_str = " ".join("'%s'" % a for a in command)
    old_env = diff.env_for(
        **extra, **({"GITHUB_STEP_SUMMARY": str(summary_old)} if summary_old else {})
    )
    new_env = diff.env_for(
        **extra,
        **({"GITHUB_STEP_SUMMARY": str(summary_new)} if summary_new else {}),
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s %s" % (TWIN, arg_str), env=old_env, timeout=60)
    new = diff.bash_streams("python3 -m %s %s" % (MODULE, arg_str), env=new_env, timeout=60)
    return (
        (old[0], _mask(old[1]), _mask(old[2])),
        (new[0], _mask(new[1]), _mask(new[2])),
    )


FAILING = ["bash", "-c", "echo gate-stdout; echo gate-stderr >&2; exit 3"]
PASSING = ["bash", "-c", "echo gate-stdout; echo gate-stderr >&2"]


def test_hard_mode_passes_through_a_clean_gate() -> None:
    old, new = run_both(PASSING, mode="hard")
    assert old == (0, "gate-stdout\n", "gate-stderr\n")
    assert new == old


def test_hard_mode_keeps_the_failing_exit_code() -> None:
    old, new = run_both(FAILING, mode="hard")
    assert old == (3, "gate-stdout\n", "gate-stderr\n")
    assert new == old
    assert "::warning::" not in old[1]


def test_soft_mode_passes_a_clean_gate_silently() -> None:
    """A soft gate that PASSES must print no warning at all: a wrapper that
    warned unconditionally would train everyone to ignore the warning."""
    old, new = run_both(PASSING, mode="soft")
    assert old == (0, "gate-stdout\n", "gate-stderr\n")
    assert new == old


def test_soft_mode_downgrades_a_failure_to_a_warning() -> None:
    old, new = run_both(FAILING, mode="soft")
    assert old[0] == 0
    assert old[1] == (
        "gate-stdout\n"
        "::warning::external gate 'bash -c echo gate-stdout; echo gate-stderr >&2; exit 3' "
        "failed (exit 3) in soft mode: external drift reported, run stays green "
        "(blocking on pull requests)\n"
    )
    assert old[2] == "gate-stderr\n"
    assert new == old


def test_soft_mode_step_summary_is_byte_identical(tmp_path: pathlib.Path) -> None:
    summary_old = tmp_path / "summary-old.md"
    summary_new = tmp_path / "summary-new.md"
    old, new = run_both(
        ["bash", "-c", "exit 7"],
        mode="soft",
        summary_old=summary_old,
        summary_new=summary_new,
    )
    assert old[0] == 0
    assert new == old
    written = summary_old.read_text(encoding="utf-8")
    assert written == (
        "### External gate soft-failed: `bash -c exit 7` (exit 7)\n"
        "\n"
        "Scheduled runs report external drift (new upstream releases,\n"
        "new advisories) as a warning instead of a red; the identical\n"
        "failure blocks on a pull request. See docs/agent-reference/ci-gates.md.\n"
    )
    assert summary_new.read_text(encoding="utf-8") == written


def test_soft_mode_summary_is_appended_not_truncated(tmp_path: pathlib.Path) -> None:
    summary_old = tmp_path / "summary-old.md"
    summary_new = tmp_path / "summary-new.md"
    for path in (summary_old, summary_new):
        path.write_text("### An earlier step wrote this\n", encoding="utf-8")
    old, new = run_both(
        ["bash", "-c", "exit 7"],
        mode="soft",
        summary_old=summary_old,
        summary_new=summary_new,
    )
    assert old[0] == 0
    assert new == old
    written = summary_old.read_text(encoding="utf-8")
    assert written.startswith("### An earlier step wrote this\n### External gate soft-failed:")
    assert summary_new.read_text(encoding="utf-8") == written


def test_hard_mode_writes_no_step_summary(tmp_path: pathlib.Path) -> None:
    summary_old = tmp_path / "summary-old.md"
    summary_new = tmp_path / "summary-new.md"
    old, new = run_both(
        ["bash", "-c", "exit 7"],
        mode="hard",
        summary_old=summary_old,
        summary_new=summary_new,
    )
    assert old[0] == 7
    assert new == old
    assert not summary_old.exists()
    assert not summary_new.exists()


def test_soft_mode_without_a_summary_file_still_exits_zero() -> None:
    old, new = run_both(["bash", "-c", "exit 7"], mode="soft")
    assert old[0] == 0
    assert "::warning::" in old[1]
    assert new == old


def test_unset_mode_is_hard_so_a_wiring_break_cannot_disable_a_gate() -> None:
    """`mode=None` removes the variable entirely, which is what a workflow that
    forgot to set it produces. Fail CLOSED."""
    old, new = run_both(FAILING, mode=None)
    assert old[0] == 3
    assert "::warning::" not in old[1]
    assert new == old


def test_empty_mode_is_also_hard() -> None:
    """`${EXTERNAL_QUALITY_MODE:-hard}` falls back on EMPTY too, so a job that
    computes the mode into an empty string still blocks."""
    old, new = run_both(FAILING, mode="")
    assert old[0] == 3
    assert "::warning::" not in old[1]
    assert new == old


def test_the_skip_state_is_refused_here_because_it_belongs_in_the_step_if() -> None:
    """`skip` is a real value of the three-state flag and it must NEVER be
    honoured by this wrapper: the step's `if:` is what implements it, so a
    `skip` arriving here means the workflow is miswired. Exit 2, not exit 0."""
    old, new = run_both(PASSING, mode="skip")
    assert old == (
        2,
        "",
        "run-external-gate: unknown EXTERNAL_QUALITY_MODE 'skip' (expected hard|soft)\n",
    )
    assert new == old


def test_unknown_mode_refuses_with_exit_two() -> None:
    old, new = run_both(PASSING, mode="Soft")
    assert old == (
        2,
        "",
        "run-external-gate: unknown EXTERNAL_QUALITY_MODE 'Soft' (expected hard|soft)\n",
    )
    assert new == old


def test_no_command_is_a_refusal() -> None:
    """An empty argument list would otherwise "succeed" at running nothing."""
    old, new = run_both([], mode="soft")
    assert old[0] == 2
    assert old[1] == ""
    assert old[2] == "usage: EXTERNAL_QUALITY_MODE=hard|soft <prog> <command...>\n"
    assert new == old


def test_the_usage_refusal_outranks_an_unknown_mode() -> None:
    """The twin checks `$#` before it validates the mode. Order preserved."""
    old, new = run_both([], mode="nonsense")
    assert old[0] == 2
    assert old[2].startswith("usage: EXTERNAL_QUALITY_MODE=hard|soft")
    assert "unknown EXTERNAL_QUALITY_MODE" not in old[2]
    assert new == old


def test_a_missing_command_exits_127_on_both_sides() -> None:
    """DIVERGENCE 2: the wording differs, the code does not. 127 is what tells
    a reader "your gate name is wrong" rather than "your gate found something"."""
    old, new = run_both(["definitely-not-a-real-binary-w7p6"], mode="hard")
    assert old[0] == 127
    assert new[0] == 127
    assert "definitely-not-a-real-binary-w7p6" in old[2]
    assert "definitely-not-a-real-binary-w7p6" in new[2]
    assert "command not found" in old[2]
    assert "command not found" in new[2]


def test_a_missing_command_is_still_softened_in_soft_mode() -> None:
    """The soft branch must not care WHY the child failed. A port that only
    softened real exit codes and let a spawn failure through would redden a
    nightly for a typo in a gate name."""
    old, new = run_both(["definitely-not-a-real-binary-w7p6"], mode="soft")
    assert old[0] == 0
    assert new[0] == 0
    assert "failed (exit 127) in soft mode" in old[1]
    assert new[1] == old[1]


def test_a_non_executable_file_exits_126_on_both_sides(tmp_path: pathlib.Path) -> None:
    """126 is "found but not executable", a different diagnosis from 127."""
    target = tmp_path / "not-executable.sh"
    target.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    old, new = run_both([str(target)], mode="hard")
    assert old[0] == 126
    assert new[0] == 126


def test_a_signalled_child_reports_128_plus_n(tmp_path: pathlib.Path) -> None:
    """DIVERGENCE 3, and the one exit-code translation this port has to do by
    hand: `subprocess` says -15, every shell says 143. A port passing the
    negative through would misreport a killed gate. bash's own `Terminated`
    notice is masked out of stderr; the code is not."""
    del tmp_path
    old, new = run_both(["bash", "-c", "kill -TERM $$"], mode="hard")
    assert old[0] == 143
    assert new[0] == 143
    assert old[2] == new[2] == ""


def test_a_signalled_child_is_softened_with_the_shell_style_code() -> None:
    old, new = run_both(["bash", "-c", "kill -TERM $$"], mode="soft")
    assert old[0] == 0
    assert "failed (exit 143) in soft mode" in old[1]
    assert new == old


def test_the_child_is_executed_not_shelled() -> None:
    """`"$@"` runs the argument vector directly, so a single argument holding a
    space names a program with a space in it. `shell=True` in the port would
    have run `echo` with an argument instead, and this case is what would catch
    it: 127 on both sides, not 0 with `hi` on stdout."""
    old, new = run_both(["echo hi"], mode="hard")
    assert old[0] == 127
    assert new[0] == 127
    assert old[1] == new[1] == ""


def test_arguments_reach_the_child_unmangled() -> None:
    old, new = run_both(["printf", "%s|%s\n", "a b", "c"], mode="hard")
    assert old == (0, "a b|c\n", "")
    assert new == old
