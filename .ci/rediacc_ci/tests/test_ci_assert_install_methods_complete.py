"""`rediacc_ci.ci.assert_install_methods_complete` against its bash twin.

Three things are compared per case, not two: stdout, stderr, the exit code AND the bytes appended to `$GITHUB_STEP_SUMMARY`. The summary is the script's real product -- it is the table a human reads in the Actions UI -- so a port that got the verdict right and the table wrong would pass a stream-only comparison. Each side writes its OWN summary file so the two cannot contaminate
each other.

`$GITHUB_STEP_SUMMARY` is a real file under `tmp_path`, never `/dev/stdout`: appending to `/dev/stdout` reopens the description and races the inherited one, which garbles both sides differently and would make the comparison a coin flip.

The K=5 ledger is
`.ci/shadow/w7p6-assert-install-methods-complete.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-assert-install-methods-complete --assert --k 5`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_ci.ci import assert_install_methods_complete as port
from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

TWIN = ".ci/scripts/ci/assert-install-methods-complete.sh"
MODULE = "rediacc_ci.ci.assert_install_methods_complete"

SUFFIXES = tuple(suffix for _, suffix in port.PLATFORMS)


def all_green() -> dict[str, str]:
    env = {"RESULT_%s" % suffix: "success" for suffix in SUFFIXES}
    env["VERSION"] = "1.2.3"
    return env


def run_both(
    tmp_path: pathlib.Path,
    env_extra: dict[str, str],
    *,
    summary: str | None = None,
    tty: str | None = None,
) -> tuple[tuple[int, str, str], tuple[int, str, str], str, str]:
    """Both sides, each with its own summary file. Returns streams plus summaries."""
    old_summary = summary if summary is not None else str(tmp_path / "old-summary.md")
    new_summary = summary if summary is not None else str(tmp_path / "new-summary.md")
    old_env = diff.env_for(**env_extra, GITHUB_STEP_SUMMARY=old_summary)
    new_env = diff.env_for(
        **env_extra,
        GITHUB_STEP_SUMMARY=new_summary,
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, tty=tty, timeout=30)
    new = diff.bash_streams("python3 -m %s" % MODULE, env=new_env, tty=tty, timeout=30)
    return old, new, read(old_summary), read(new_summary)


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return "<no summary written>"


def assert_identical(
    tmp_path: pathlib.Path, env_extra: dict[str, str], *, expect_exit: int
) -> tuple[tuple[int, str, str], str]:
    old, new, old_summary, new_summary = run_both(tmp_path, env_extra)
    assert old[0] == expect_exit, "twin exit changed: %r" % (old,)
    assert new[0] == old[0]
    assert new[1] == old[1]
    assert new[2] == old[2]
    assert new_summary == old_summary
    return old, old_summary


def test_all_six_platforms_green(tmp_path: pathlib.Path) -> None:
    old, summary = assert_identical(tmp_path, all_green(), expect_exit=0)
    assert old[2] == "✓ All installation method tests passed for version 1.2.3\n"
    assert old[1] == ""
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


def test_the_platform_table_still_matches_the_twins(tmp_path: pathlib.Path) -> None:
    """The label|suffix pairs are a COPY of the twin's array. Re-read the twin.

    Parsed out of the bash rather than restated, so the port and the test cannot drift together away from the file CI runs. `tmp_path` is unused here and kept for signature symmetry with the rest of the file.
    """
    del tmp_path
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        block = fh.read().split("PLATFORMS=(", 1)[1].split("\n)", 1)[0]
    pairs = tuple(
        tuple(line.strip().strip('"').split("|"))
        for line in block.splitlines()
        if line.strip().startswith('"')
    )
    assert pairs == port.PLATFORMS


def test_one_failure_blocks_and_names_it(tmp_path: pathlib.Path) -> None:
    env = all_green()
    env["RESULT_WINDOWS_ARM64"] = "failure"
    old, summary = assert_identical(tmp_path, env, expect_exit=1)
    assert old[2] == "✗ Some installation method tests failed\n"
    assert "| Windows arm64 (Binary) | failure |\n" in summary
    assert summary.endswith("**Status:** Some installation method tests failed\n")


def test_skipped_is_not_accepted_here(tmp_path: pathlib.Path) -> None:
    """Unlike the soft tier in assert-ci-complete.sh. Every platform is hard."""
    env = all_green()
    env["RESULT_MACOS_X64"] = "skipped"
    _, summary = assert_identical(tmp_path, env, expect_exit=1)
    assert "| macOS x64 (Binary, Homebrew) | skipped |\n" in summary


def test_an_empty_result_reads_as_unset_and_fails(tmp_path: pathlib.Path) -> None:
    env = all_green()
    env["RESULT_LINUX_ARM64"] = ""
    _, summary = assert_identical(tmp_path, env, expect_exit=1)
    assert "| Linux arm64 (Binary, Docker, Quick) | <unset> |\n" in summary


def test_an_empty_environment_is_a_failure_not_a_pass(tmp_path: pathlib.Path) -> None:
    _, summary = assert_identical(tmp_path, {}, expect_exit=1)
    assert summary.count("| <unset> |") == len(port.PLATFORMS)


def test_a_missing_version_renders_as_unset_in_the_green_line(tmp_path: pathlib.Path) -> None:
    env = all_green()
    del env["VERSION"]
    old, summary = assert_identical(tmp_path, env, expect_exit=0)
    assert old[2] == "✓ All installation method tests passed for version <unset>\n"
    assert summary.endswith(
        "**Status:** All installation method tests passed for version <unset>\n"
    )


def test_an_empty_version_also_renders_as_unset(tmp_path: pathlib.Path) -> None:
    env = all_green()
    env["VERSION"] = ""
    old, _ = assert_identical(tmp_path, env, expect_exit=0)
    assert "version <unset>" in old[2]


def test_the_summary_is_appended_not_truncated(tmp_path: pathlib.Path) -> None:
    """`>>`, so an earlier step's section must survive underneath."""
    preamble = "## Earlier step\n\nkeep me\n"
    for name in ("old-summary.md", "new-summary.md"):
        (tmp_path / name).write_text(preamble, encoding="utf-8")
    _, summary = assert_identical(tmp_path, all_green(), expect_exit=0)
    assert summary.startswith(preamble)


def test_no_summary_variable_writes_to_dev_null_and_still_judges(
    tmp_path: pathlib.Path,
) -> None:
    """`${GITHUB_STEP_SUMMARY:-/dev/null}`: the table is discarded, not put on stdout."""
    del tmp_path
    env = all_green()
    env["RESULT_LINUX_X64"] = "failure"
    old_env = diff.env_for(**env)
    new_env = diff.env_for(**env, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m %s" % MODULE, env=new_env, timeout=30)
    assert old[0] == new[0] == 1
    assert old[1] == "", "the table must not leak onto stdout"
    assert new[1] == "", "the table must not leak onto stdout"
    assert new[2] == old[2]


def test_an_empty_summary_variable_is_also_dev_null(tmp_path: pathlib.Path) -> None:
    del tmp_path
    env = all_green()
    old_env = diff.env_for(**env, GITHUB_STEP_SUMMARY="")
    new_env = diff.env_for(
        **env, GITHUB_STEP_SUMMARY="", PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"
    )
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m %s" % MODULE, env=new_env, timeout=30)
    assert old[0] == new[0] == 0
    assert new[1] == old[1]
    assert new[2] == old[2]


def test_an_unwritable_summary_refuses_before_judging_anything(tmp_path: pathlib.Path) -> None:
    """REWORDED, NOT BYTE-IDENTICAL, and the only such case in this file.

    The twin dies at its first redirect under `set -e` with a bare shell diagnostic carrying a bash line number. Both sides must exit 1, print nothing to stdout, name the path and name the OS error, and neither may reach the verdict lines.
    """
    unwritable = str(tmp_path / "nonexistent-dir" / "summary.md")
    old, new, _, _ = run_both(tmp_path, all_green(), summary=unwritable)
    assert old[0] == 1
    assert new[0] == 1
    assert old[1] == ""
    assert new[1] == ""
    for stderr in (old[2], new[2]):
        assert unwritable in stderr
        assert "No such file or directory" in stderr
        assert "installation method tests" not in stderr


def test_colour_on_a_terminal_is_byte_identical(tmp_path: pathlib.Path) -> None:
    env = all_green()
    env["RESULT_LINUX_X64"] = "failure"
    old, new, old_summary, new_summary = run_both(tmp_path, env, tty="stderr")
    assert old[0] == new[0] == 1
    assert diff.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert new[2] == old[2]
    assert new_summary == old_summary
    assert diff.escape_bytes(old_summary) == 0, "colour must never reach the summary file"
