"""`rediacc_ci.ci.assert_install_methods_complete`, driven against the bytes its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/ci/assert-install-methods-complete.sh` and the port over the same environment and compared four things, not three: stdout, stderr, the exit code AND the bytes appended to `$GITHUB_STEP_SUMMARY`. The K=5 ledger `.ci/shadow/w7p6-assert-install-methods-complete.observations.jsonl` recorded that comparison over five
distinct trees. The twin has now been deleted and every case that executed it compares against `goldens/assert-install-methods-complete/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

THE SUMMARY IS THE SCRIPT'S REAL PRODUCT -- it is the table a human reads in the Actions UI -- so a port that got the verdict right and the table wrong would pass a stream-only comparison. Every golden therefore carries a fourth `--- summary ---` section holding the file's bytes, and each run writes its OWN summary file so no two runs can contaminate each other.

`$GITHUB_STEP_SUMMARY` is a real file under `tmp_path`, never `/dev/stdout`: appending to `/dev/stdout` reopens the description and races the inherited one, which garbles the output and would make the comparison a coin flip.

THE STALENESS ALARM THAT PARSED THE TWIN'S `PLATFORMS=(` ARRAY IS GONE, and the recorded table replaces it. It existed so the port's copy of the label|suffix pairs could not drift away from the array CI ran; the recorded summary names all six labels in the twin's own order, which is the same claim made against bytes the twin actually wrote.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from rediacc_ci.ci import assert_install_methods_complete as port
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

SLUG = "assert-install-methods-complete"
MODULE = "rediacc_ci.ci.assert_install_methods_complete"

SUFFIXES = tuple(suffix for _, suffix in port.PLATFORMS)

SUMMARY_MARKER = "--- summary ---\n"
# Ends in a newline so a golden that ends on it keeps the final newline check:editorconfig requires of every text file. This is the test's own placeholder, not a byte the twin recorded.
NO_SUMMARY = "<no summary written>\n"

# `>>`, so an earlier step's section must survive underneath. One case pre-writes this.
PREAMBLE = "## Earlier step\n\nkeep me\n"


def all_green() -> dict[str, str]:
    env = {"RESULT_%s" % suffix: "success" for suffix in SUFFIXES}
    env["VERSION"] = "1.2.3"
    return env


def case_env(name: str) -> dict[str, str]:
    """One recorded case's environment overrides, rebuilt fresh."""
    env = all_green()
    if name == "all-six-platforms-green":
        return env
    if name == "one-platform-failed":
        env["RESULT_WINDOWS_ARM64"] = "failure"
        return env
    if name == "a-skipped-platform":
        env["RESULT_MACOS_X64"] = "skipped"
        return env
    if name == "an-empty-result":
        env["RESULT_LINUX_ARM64"] = ""
        return env
    if name == "an-empty-environment":
        return {}
    if name == "a-missing-version":
        del env["VERSION"]
        return env
    if name == "an-empty-version":
        env["VERSION"] = ""
        return env
    if name == "the-summary-is-appended":
        return env
    if name in ("no-summary-variable", "colour-on-a-terminal"):
        env["RESULT_LINUX_X64"] = "failure"
        return env
    if name == "an-empty-summary-variable":
        return env
    if name == "an-unwritable-summary":
        return env
    raise KeyError(name)


# How each case wires `$GITHUB_STEP_SUMMARY`: a real file, absent, empty, or a path under a directory that does not exist.
SUMMARY_MODE = {
    "no-summary-variable": "absent",
    "an-empty-summary-variable": "empty",
    "an-unwritable-summary": "unwritable",
}

TTY = {"colour-on-a-terminal": "stderr"}

CASES = (
    "all-six-platforms-green",
    "one-platform-failed",
    "a-skipped-platform",
    "an-empty-result",
    "an-empty-environment",
    "a-missing-version",
    "an-empty-version",
    "the-summary-is-appended",
    "no-summary-variable",
    "an-empty-summary-variable",
    "an-unwritable-summary",
    "colour-on-a-terminal",
)

# The one case the port does not reproduce byte for byte: the twin died at its first redirect under `set -e` with a bare shell diagnostic carrying a bash line number. Compared by shape, in its own test.
REWORDED = "an-unwritable-summary"


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return NO_SUMMARY


def run(
    tmp_path: pathlib.Path, name: str, command: str, *, tag: str = "new"
) -> tuple[int, str, str, str]:
    """One side, once, with its own summary file."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    mode = SUMMARY_MODE.get(name, "file")
    summary = str(tmp_path / ("%s-summary.md" % tag))
    if mode == "unwritable":
        summary = str(tmp_path / "nonexistent-dir" / "summary.md")
    elif mode == "empty":
        summary = ""
    if name == "the-summary-is-appended":
        (tmp_path / ("%s-summary.md" % tag)).write_text(PREAMBLE, encoding="utf-8")

    overrides = dict(case_env(name))
    if mode != "absent":
        overrides["GITHUB_STEP_SUMMARY"] = summary
    if command.startswith("python3"):
        overrides["PYTHONPATH"] = ".ci"
        overrides["PYTHONDONTWRITEBYTECODE"] = "1"
    returncode, stdout, stderr = diff.bash_streams(
        command, env=diff.env_for(**overrides), tty=TTY.get(name), timeout=30
    )
    written = read(summary) if mode in ("file", "unwritable") else NO_SUMMARY
    return returncode, stdout, stderr, written


def render(returncode: int, stdout: str, stderr: str, summary: str, root: pathlib.Path) -> str:
    body = frozen.render(returncode, frozen.mask_root(stdout, root), frozen.mask_root(stderr, root))
    return body + SUMMARY_MARKER + frozen.mask_root(summary, root)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    streams, summary = rest.split(SUMMARY_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, summary


def drive(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    returncode, stdout, stderr, summary = run(tmp_path, name, "python3 -m %s" % MODULE)
    return (
        returncode,
        frozen.mask_root(stdout, tmp_path / "new-summary.md"),
        frozen.mask_root(stderr, tmp_path / "new-summary.md"),
        frozen.mask_root(summary, tmp_path / "new-summary.md"),
    )


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = drive(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged from the recorded bytes" % name
    assert got[2] == want[2], "%s: stderr diverged from the recorded bytes" % name
    assert got[3] == want[3], "%s: the step summary diverged from the recorded bytes" % name
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c != REWORDED])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_all_six_platforms_green() -> None:
    returncode, stdout, stderr, summary = recorded("all-six-platforms-green")
    assert returncode == 0
    assert stderr == "✓ All installation method tests passed for version 1.2.3\n"
    assert stdout == ""
    assert summary == (
        "## Install Method Test Results\n"
        "\n"
        "| Platform | Result |\n"
        "|----------|--------|\n"
        "| Linux x64 (Binary, Docker, APT, DNF, APK, Pacman, Quick, Linuxbrew) | success |\n"
        "| Linux arm64 (Binary, Docker, Quick) | success |\n"
        "| macOS ARM64 (Binary, Homebrew) | success |\n"
        "| macOS x64 (Binary, Homebrew) | success |\n"
        "| Windows x64 (Binary) | success |\n"
        "| Windows arm64 (Binary) | success |\n"
        "\n"
        "**Status:** All installation method tests passed for version 1.2.3\n"
    )


def test_the_platform_table_still_matches_the_twins() -> None:
    """The label|suffix pairs are a COPY of the twin's array, and the recorded table is what keeps the copy honest.

    Parsed out of the RECORDING rather than restated, so the port and this test cannot drift together away from the six rows the twin really wrote.
    """
    summary = recorded("all-six-platforms-green")[3]
    rows = [line for line in summary.splitlines() if line.startswith("| ") and "|----" not in line]
    labels = [row.split(" | ")[0].removeprefix("| ") for row in rows[1:]]
    assert labels == [label for label, _ in port.PLATFORMS]


def test_one_failure_blocks_and_names_it() -> None:
    returncode, _, stderr, summary = recorded("one-platform-failed")
    assert returncode == 1
    assert stderr == "✗ Some installation method tests failed\n"
    assert "| Windows arm64 (Binary) | failure |\n" in summary
    assert summary.endswith("**Status:** Some installation method tests failed\n")


def test_skipped_is_not_accepted_here() -> None:
    """Unlike the soft tier in `assert_ci_complete`. Every platform is hard."""
    returncode, _, _, summary = recorded("a-skipped-platform")
    assert returncode == 1
    assert "| macOS x64 (Binary, Homebrew) | skipped |\n" in summary


def test_an_empty_result_reads_as_unset_and_fails() -> None:
    returncode, _, _, summary = recorded("an-empty-result")
    assert returncode == 1
    assert "| Linux arm64 (Binary, Docker, Quick) | <unset> |\n" in summary


def test_an_empty_environment_is_a_failure_not_a_pass() -> None:
    returncode, _, _, summary = recorded("an-empty-environment")
    assert returncode == 1
    assert summary.count("| <unset> |") == len(port.PLATFORMS)


def test_a_missing_version_renders_as_unset_in_the_green_line() -> None:
    returncode, _, stderr, summary = recorded("a-missing-version")
    assert returncode == 0
    assert stderr == "✓ All installation method tests passed for version <unset>\n"
    assert summary.endswith(
        "**Status:** All installation method tests passed for version <unset>\n"
    )


def test_an_empty_version_also_renders_as_unset() -> None:
    returncode, _, stderr, _ = recorded("an-empty-version")
    assert returncode == 0
    assert "version <unset>" in stderr


def test_the_summary_is_appended_not_truncated() -> None:
    """`>>`, so an earlier step's section must survive underneath."""
    summary = recorded("the-summary-is-appended")[3]
    assert summary.startswith(PREAMBLE)
    assert "## Install Method Test Results\n" in summary


def test_no_summary_variable_writes_to_dev_null_and_still_judges() -> None:
    """`${GITHUB_STEP_SUMMARY:-/dev/null}`: the table was discarded, not put on stdout."""
    returncode, stdout, _, summary = recorded("no-summary-variable")
    assert returncode == 1
    assert stdout == "", "the table must not leak onto stdout"
    assert summary == NO_SUMMARY


def test_an_empty_summary_variable_is_also_dev_null() -> None:
    returncode, stdout, _, summary = recorded("an-empty-summary-variable")
    assert returncode == 0
    assert stdout == ""
    assert summary == NO_SUMMARY


def test_an_unwritable_summary_refuses_before_judging_anything(tmp_path: pathlib.Path) -> None:
    """REWORDED, NOT BYTE-IDENTICAL, and the only such case in this file.

    The twin died at its first redirect under `set -e` with a bare shell diagnostic carrying a bash line number. Both the recording and the port must exit 1, print nothing to stdout, name the path and name the OS error, and neither may reach the verdict lines.
    """
    want_exit, want_out, want_err, _ = recorded(REWORDED)
    returncode, stdout, stderr, _ = drive(tmp_path, REWORDED)
    assert want_exit == 1
    assert returncode == 1
    assert want_out == ""
    assert stdout == ""
    for text in (want_err, stderr):
        assert "nonexistent-dir/summary.md" in text
        assert "No such file or directory" in text
        assert "installation method tests" not in text


def test_colour_on_a_terminal_is_byte_identical(tmp_path: pathlib.Path) -> None:
    returncode, _, stderr, summary = recorded("colour-on-a-terminal")
    assert returncode == 1
    assert diff.escape_bytes(stderr) > 0, "the twin printed no colour on a tty"
    assert diff.escape_bytes(summary) == 0, "colour must never reach the summary file"
    compare(tmp_path, "colour-on-a-terminal")


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_acceptance_of_skipped_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Treat `skipped` as a pass.

    `assert_ci_complete` one file over DOES have a soft tier, so accepting `skipped` here reads as consistency rather than as a hole, and it is the change that lets a platform whose whole job was skipped count as tested. The recorded verdict for `a-skipped-platform` is 1, and the recorded status line says the tests failed; a mutant that accepts it prints the green line
    instead. The mutation runs from a throwaway copy of the package's module file; the tracked port is never touched.
    """
    source = port.__file__
    with open(source, encoding="utf-8") as fh:
        original = fh.read()
    anchor = '            if value != "success":\n'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, '            if value not in ("success", "skipped"):\n')

    mutant_dir = tmp_path / "mutant"
    mutant_dir.mkdir(parents=True, exist_ok=True)
    mutant = mutant_dir / "assert_install_methods_complete.py"
    mutant.write_text(mutated, encoding="utf-8")

    overrides = dict(case_env("a-skipped-platform"))
    overrides["GITHUB_STEP_SUMMARY"] = str(mutant_dir / "summary.md")
    overrides["PYTHONPATH"] = ".ci"
    overrides["PYTHONDONTWRITEBYTECODE"] = "1"
    returncode, _, stderr = diff.bash_streams(
        "python3 %s" % mutant, env=diff.env_for(**overrides), timeout=30
    )
    want_exit, _, want_err, _ = recorded("a-skipped-platform")
    assert want_exit == 1, "the recorded verdict for a skipped platform moved"
    assert returncode == 0, "the plant did not change the verdict"
    assert stderr != want_err, "the plant is invisible on stderr"

    compare(tmp_path / "good", "a-skipped-platform")
    with open(source, encoding="utf-8") as fh:
        assert fh.read() == original
