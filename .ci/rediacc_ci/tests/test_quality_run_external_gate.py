"""`rediacc_ci.quality.run_external_gate`, driven directly against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/run-external-gate.sh` over each case below and its bytes were compared against the port's. The K=5 ledger `.ci/shadow/w7p6-run-external-gate.observations.jsonl` recorded that verdict over five distinct trees and licensed the port.

The twin has now been deleted, and every case compares against `goldens/run-external-gate/`, which holds the twin's OWN recorded output. The provenance header of each golden carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed those bytes.

ALL THREE STATES OF THE FLAG ARE DRIVEN, plus the two the flag can be in by accident. `hard` and `soft` are the two this wrapper ever legitimately sees, since `skip` is expressed in the step's `if:` and never reaches the script. The cases below cover hard/pass, hard/fail, soft/pass, soft/fail, UNSET (must be hard, because a wiring break disabling a blocking gate silently is the
failure this wrapper exists to prevent), EMPTY (same), and an unrecognised value including the literal `skip`, which must refuse with exit 2.

THE EXIT CODE IS THE ASSERTION, not the prose, because the exit code is what decides red versus green. Three cases exist only to pin codes a port can plausibly get wrong: 127 for a command that is not on PATH, 126 for a file that is there but not executable, and 143 for a child killed by SIGTERM, which `subprocess` reports as `-15` and every shell reports as `128 + 15`. A port
passing the negative number through would turn a killed gate into something other than a failure.

THREE MESSAGE-TEXT DIVERGENCES ARE EXPECTED AND DECLARED RATHER THAN IGNORED, one per case: the `$0` in the usage line, the spawn-failure wording, and bash's own `Terminated` job-control notice, which has no Python equivalent. The first and third are masked on both sides. The second cannot be masked, so those cases carry `COMPARE_STDOUT` or `COMPARE_EXIT` and a named test of their
own that asserts what each side must say.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

SLUG = "run-external-gate"
MODULE = "rediacc_ci.quality.run_external_gate"
PORT = pathlib.Path(diff.repo()) / ".ci" / "rediacc_ci" / "quality" / "run_external_gate.py"

# Divergence 1: the usage line interpolates `$0`, and a module invoked as `python3 -m ...` cannot have the same program path.
PROGRAM_RE = re.compile(r"EXTERNAL_QUALITY_MODE=hard\|soft \S+ <command\.\.\.>")
# Divergence 3: bash announces a signalled child on its own stderr.
TERMINATED_RE = re.compile(r"^Terminated\s+.*$\n?", re.MULTILINE)

ABSENT = "(absent)\n"
EARLIER = "### An earlier step wrote this\n"

FAILING = ["bash", "-c", "echo gate-stdout; echo gate-stderr >&2; exit 3"]
PASSING = ["bash", "-c", "echo gate-stdout; echo gate-stderr >&2"]
EXIT_SEVEN = ["bash", "-c", "exit 7"]
ABSENT_BINARY = "definitely-not-a-real-binary-w7p6"

COMPARE_ALL = "all"
COMPARE_STDOUT = "stdout"
COMPARE_EXIT = "exit"


def mask(text: str) -> str:
    text = PROGRAM_RE.sub("EXTERNAL_QUALITY_MODE=hard|soft <prog> <command...>", text)
    return TERMINATED_RE.sub("", text)


def render(returncode: int, stdout: str, stderr: str, summary: str) -> str:
    return "%s--- summary ---\n%s" % (
        frozen.render(returncode, mask(stdout), mask(stderr)),
        summary,
    )


def split_golden(text: str) -> tuple[int, str, str, str]:
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, summary = rest.split("--- summary ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, summary


def run_port(
    tmp_path: pathlib.Path,
    command: list[str],
    mode: str | None = None,
    summary: str | None = None,
    port: str | None = None,
) -> tuple[int, str, str, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    extra: dict[str, str] = {}
    if mode is not None:
        extra["EXTERNAL_QUALITY_MODE"] = mode
    summary_path = tmp_path / "summary.md"
    if summary is not None:
        extra["GITHUB_STEP_SUMMARY"] = str(summary_path)
        if summary:
            summary_path.write_text(summary, encoding="utf-8")
    env = diff.env_for(**extra, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    invocation = "python3 -m %s" % MODULE if port is None else "python3 %s" % port
    arg_str = " ".join("'%s'" % a for a in command)
    returncode, stdout, stderr = diff.bash_streams(
        "%s %s" % (invocation, arg_str), env=env, timeout=60
    )
    written = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ABSENT
    return returncode, mask(stdout), mask(stderr), written


CASES: list[tuple[str, str, dict[str, object]]] = [
    ("hard-mode-passes-through-a-clean-gate", COMPARE_ALL, {"command": PASSING, "mode": "hard"}),
    ("hard-mode-keeps-the-failing-exit-code", COMPARE_ALL, {"command": FAILING, "mode": "hard"}),
    # A soft gate that PASSES must print no warning at all: a wrapper that warned unconditionally would train everyone to ignore the warning.
    ("soft-mode-passes-a-clean-gate-silently", COMPARE_ALL, {"command": PASSING, "mode": "soft"}),
    (
        "soft-mode-downgrades-a-failure-to-a-warning",
        COMPARE_ALL,
        {"command": FAILING, "mode": "soft"},
    ),
    (
        "soft-mode-writes-the-step-summary",
        COMPARE_ALL,
        {"command": EXIT_SEVEN, "mode": "soft", "summary": ""},
    ),
    (
        "the-soft-summary-is-appended-not-truncated",
        COMPARE_ALL,
        {"command": EXIT_SEVEN, "mode": "soft", "summary": EARLIER},
    ),
    (
        "hard-mode-writes-no-step-summary",
        COMPARE_ALL,
        {"command": EXIT_SEVEN, "mode": "hard", "summary": ""},
    ),
    (
        "soft-mode-without-a-summary-file-still-exits-zero",
        COMPARE_ALL,
        {"command": EXIT_SEVEN, "mode": "soft"},
    ),
    # `mode=None` removes the variable entirely, which is what a workflow that forgot to set it produces. Fail CLOSED.
    ("unset-mode-is-hard", COMPARE_ALL, {"command": FAILING}),
    # `${EXTERNAL_QUALITY_MODE:-hard}` falls back on EMPTY too, so a job that computes the mode into an empty string still blocks.
    ("empty-mode-is-also-hard", COMPARE_ALL, {"command": FAILING, "mode": ""}),
    # `skip` is a real value of the three-state flag and it must NEVER be honoured here: the step's `if:` is what implements it, so a `skip` arriving here means the workflow is miswired. Exit 2, not exit 0.
    ("the-skip-state-is-refused-here", COMPARE_ALL, {"command": PASSING, "mode": "skip"}),
    ("unknown-mode-refuses-with-exit-two", COMPARE_ALL, {"command": PASSING, "mode": "Soft"}),
    # An empty argument list would otherwise "succeed" at running nothing.
    ("no-command-is-a-refusal", COMPARE_ALL, {"command": [], "mode": "soft"}),
    # The twin checks `$#` before it validates the mode. Order preserved.
    (
        "the-usage-refusal-outranks-an-unknown-mode",
        COMPARE_ALL,
        {"command": [], "mode": "nonsense"},
    ),
    # DIVERGENCE 2: the spawn-failure wording differs, the code does not.
    ("a-missing-command-exits-127", COMPARE_STDOUT, {"command": [ABSENT_BINARY], "mode": "hard"}),
    (
        "a-missing-command-is-still-softened",
        COMPARE_STDOUT,
        {"command": [ABSENT_BINARY], "mode": "soft"},
    ),
    # 126 is "found but not executable", a different diagnosis from 127. The path is a tempdir, so only the code is compared.
    ("a-non-executable-file-exits-126", COMPARE_EXIT, {"command": None, "mode": "hard"}),
    # DIVERGENCE 3, and the one exit-code translation this port does by hand.
    (
        "a-signalled-child-reports-128-plus-n",
        COMPARE_ALL,
        {"command": ["bash", "-c", "kill -TERM $$"], "mode": "hard"},
    ),
    (
        "a-signalled-child-is-softened-with-the-shell-style-code",
        COMPARE_ALL,
        {"command": ["bash", "-c", "kill -TERM $$"], "mode": "soft"},
    ),
    # `"$@"` runs the argument vector directly, so a single argument holding a space names a program with a space in it. `shell=True` in the port would have run `echo` with an argument instead.
    ("the-child-is-executed-not-shelled", COMPARE_STDOUT, {"command": ["echo hi"], "mode": "hard"}),
    (
        "arguments-reach-the-child-unmangled",
        COMPARE_ALL,
        {"command": ["printf", "%s|%s\n", "a b", "c"], "mode": "hard"},
    ),
]

# The one case whose command is built per run, because it needs a real file on disk that is present and not executable.
NON_EXECUTABLE = "a-non-executable-file-exits-126"


def materialise(tmp_path: pathlib.Path, kwargs: dict[str, object]) -> dict[str, object]:
    """Fill in the one case whose argument vector cannot be a constant."""
    if kwargs.get("command") is not None:
        return kwargs
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "not-executable.sh"
    target.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    return dict(kwargs, command=[str(target)])


@pytest.mark.parametrize(("name", "how", "kwargs"), CASES, ids=[c[0] for c in CASES])
def test_port_matches_the_twins_recorded_output(
    tmp_path: pathlib.Path, name: str, how: str, kwargs: dict[str, object]
) -> None:
    want_exit, want_out, want_err, want_summary = split_golden(frozen.read(SLUG, name))
    returncode, stdout, stderr, summary = run_port(
        tmp_path / "run", **materialise(tmp_path / "fix", kwargs)
    )  # type: ignore[arg-type]
    assert returncode == want_exit, "%s: the twin exited %d, the port %d" % (
        name,
        want_exit,
        returncode,
    )
    if how == COMPARE_EXIT:
        return
    assert stdout == want_out, "%s: stdout diverged from the twin's recorded bytes" % name
    assert summary == want_summary, "%s: the step summary diverged" % name
    if how == COMPARE_STDOUT:
        return
    assert stderr == want_err, "%s: stderr diverged from the twin's recorded bytes" % name


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {name for name, _, _ in CASES})


def test_the_recording_is_a_wrapper_at_work_and_not_a_banner() -> None:
    """ANTI-VACUITY on the recording itself. Two programs that print nothing agree about nothing, so the load-bearing bytes are named here."""
    hard = frozen.read(SLUG, "hard-mode-keeps-the-failing-exit-code")
    soft = frozen.read(SLUG, "soft-mode-downgrades-a-failure-to-a-warning")
    assert hard.startswith("exit: 3\n")
    assert "::warning::" not in hard, "a hard failure must not carry the soft warning"
    assert soft.startswith("exit: 0\n")
    assert (
        "::warning::external gate 'bash -c echo gate-stdout; echo gate-stderr >&2; exit 3' "
        "failed (exit 3) in soft mode: external drift reported, run stays green "
        "(blocking on pull requests)\n"
    ) in soft

    summary = split_golden(frozen.read(SLUG, "soft-mode-writes-the-step-summary"))[3]
    assert summary == (
        "### External gate soft-failed: `bash -c exit 7` (exit 7)\n"
        "\n"
        "Scheduled runs report external drift (new upstream releases,\n"
        "new advisories) as a warning instead of a red; the identical\n"
        "failure blocks on a pull request. See docs/agent-reference/ci-gates.md.\n"
    )
    appended = split_golden(frozen.read(SLUG, "the-soft-summary-is-appended-not-truncated"))[3]
    assert appended.startswith("%s### External gate soft-failed:" % EARLIER)
    assert split_golden(frozen.read(SLUG, "hard-mode-writes-no-step-summary"))[3] == ABSENT

    for name in ("the-skip-state-is-refused-here", "unknown-mode-refuses-with-exit-two"):
        refusal = frozen.read(SLUG, name)
        assert refusal.startswith("exit: 2\n")
        assert "run-external-gate: unknown EXTERNAL_QUALITY_MODE" in refusal
    usage = "usage: EXTERNAL_QUALITY_MODE=hard|soft <prog> <command...>\n"
    assert usage in frozen.read(SLUG, "no-command-is-a-refusal")
    outranked = frozen.read(SLUG, "the-usage-refusal-outranks-an-unknown-mode")
    assert usage in outranked
    assert "unknown EXTERNAL_QUALITY_MODE" not in outranked


def test_a_missing_command_is_127_with_its_wording_declared(
    tmp_path: pathlib.Path,
) -> None:
    """DIVERGENCE 2: the wording differs, the code does not. 127 is what tells a reader "the gate name is wrong" rather than "the gate found something"."""
    recorded_exit, _, recorded_err, _ = split_golden(
        frozen.read(SLUG, "a-missing-command-exits-127")
    )
    returncode, _, stderr, _ = run_port(tmp_path, [ABSENT_BINARY], mode="hard")
    assert recorded_exit == returncode == 127
    for text in (recorded_err, stderr):
        assert ABSENT_BINARY in text
        assert "command not found" in text


def test_a_missing_command_is_still_softened_in_soft_mode(tmp_path: pathlib.Path) -> None:
    """The soft branch must not care WHY the child failed. A port that only softened real exit codes and let a spawn failure through would redden a nightly for a typo in a gate name."""
    recorded_exit, recorded_out, _, _ = split_golden(
        frozen.read(SLUG, "a-missing-command-is-still-softened")
    )
    returncode, stdout, _, _ = run_port(tmp_path, [ABSENT_BINARY], mode="soft")
    assert recorded_exit == returncode == 0
    assert "failed (exit 127) in soft mode" in recorded_out
    assert stdout == recorded_out


def test_a_signalled_child_reports_128_plus_n(tmp_path: pathlib.Path) -> None:
    """`subprocess` says -15, every shell says 143. A port passing the negative through would misreport a killed gate. bash's own `Terminated` notice is masked out of stderr; the code is not."""
    recorded_exit, _, recorded_err, _ = split_golden(
        frozen.read(SLUG, "a-signalled-child-reports-128-plus-n")
    )
    returncode, _, stderr, _ = run_port(tmp_path, ["bash", "-c", "kill -TERM $$"], mode="hard")
    assert recorded_exit == returncode == 143
    assert recorded_err == stderr == ""


def test_planted_defect_is_caught_by_the_goldens(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Report a signalled child the way `subprocess` does.

    Returning the raw negative status is exactly what a port gets for free, and the shell-style `128 + n` translation is the one arithmetic this wrapper has to do by hand. The mutation is written to a throwaway file; the tracked port is never touched.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = "    return 128 + (-returncode) if returncode < 0 else returncode\n"
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken_src = source.replace(anchor, "    return returncode\n")
    assert broken_src != source

    broken = tmp_path / "run_external_gate_broken.py"
    broken.write_text(broken_src, encoding="utf-8")
    command = ["bash", "-c", "kill -TERM $$"]
    recorded_exit = split_golden(frozen.read(SLUG, "a-signalled-child-reports-128-plus-n"))[0]
    broken_exit = run_port(tmp_path / "broken", command, mode="hard", port=str(broken))[0]
    assert broken_exit != recorded_exit, (
        "PLANT DID NOT FIRE: the goldens cannot see a signalled child misreported"
    )
    # And the real, unmutated file still agrees against the same case.
    assert run_port(tmp_path / "real", command, mode="hard")[0] == recorded_exit
    assert PORT.read_text(encoding="utf-8") == source
