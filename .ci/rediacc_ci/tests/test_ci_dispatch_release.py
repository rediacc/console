"""`rediacc_ci.ci.dispatch_release` against its bash twin.

BOTH SIDES ARE DRIVEN THROUGH ONE RECORDING FAKE `gh` on a scratch PATH. The twin never runs `gh` in a way a test could safely let reach GitHub -- the decide path is a real API read and the dispatch path STARTS A RELEASE -- so the fake is not a convenience, it is the only way this differential can exist. It logs its own argv as `call: gh ...` on stderr and answers from three
environment variables:

    FAKE_GH_STDOUT       the `gh api` body, on stdout
    FAKE_GH_STDERR       a `gh api` diagnostic, on stderr
    FAKE_GH_RC           the `gh api` exit status
    FAKE_GH_RUN_STDERR   a `gh workflow run` diagnostic
    FAKE_GH_RUN_RC       the `gh workflow run` exit status
    FAKE_GH_ECHO         `stderr` (default), `dispatch`, or `none`

THE TWO SUBCOMMANDS ANSWER SEPARATELY, and that is not tidiness. A fake that echoed one body for both would feed the PR table back through `gh workflow run`, and a fake that logged its call line for both would feed the LOG LINE into the PR table -- which is Defect A, and which turns every decide
case into a measurement of the fake. `FAKE_GH_ECHO=dispatch` logs only the
uncaptured `gh workflow run` call, which is the mode the ledger uses; `none` logs nothing; `stderr` logs both, and exactly one case wants that, to prove the pollution is real rather than assumed.

The `call:` line is also what makes a shadow-gate ledger possible for this pair. `shadow-gate.ts` classifies `→ ` and `✓ ` as CHATTER before any `--finding-re` is consulted, and this script reports almost entirely through `log_info`, so no message-text regex could ever produce a finding. The ledger is recorded with `--finding-re '^(call: |decision: |DRY-RUN: )'`.

The K=5 ledger is `.ci/shadow/w7p6-dispatch-release.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-dispatch-release --assert --k 5`).
"""

from __future__ import annotations

import os
import shlex
import stat
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.ci import dispatch_release as port
from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/ci/dispatch-release.sh"
MODULE = "rediacc_ci.ci.dispatch_release"

FAKE_GH = """#!/bin/bash
mode="${FAKE_GH_ECHO:-stderr}"
if [[ "$mode" == "stderr" ]] || { [[ "$mode" == "dispatch" ]] && [[ "$1" != "api" ]]; }; then
  printf 'call: gh' >&2
  for a in "$@"; do printf ' %s' "$a" >&2; done
  printf '\\n' >&2
fi
if [[ "$1" == "api" ]]; then
  [[ -n "${FAKE_GH_STDERR:-}" ]] && printf '%s\\n' "$FAKE_GH_STDERR" >&2
  [[ -n "${FAKE_GH_STDOUT:-}" ]] && printf '%s\\n' "$FAKE_GH_STDOUT"
  exit "${FAKE_GH_RC:-0}"
fi
[[ -n "${FAKE_GH_RUN_STDERR:-}" ]] && printf '%s\\n' "$FAKE_GH_RUN_STDERR" >&2
exit "${FAKE_GH_RUN_RC:-0}"
"""

BASE = {
    "GITHUB_REPOSITORY": "rediacc/console",
    "GITHUB_SHA": "abcdef1234567890abcdef1234567890abcdef12",
    "FAKE_GH_ECHO": "none",
}


@pytest.fixture(scope="module")
def bindir(tmp_path_factory) -> pathlib.Path:
    """The recording fake, once per module."""
    root = tmp_path_factory.mktemp("dispatch-release-bin")
    script = root / "gh"
    script.write_text(FAKE_GH, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return root


def run_both(
    bindir: pathlib.Path,
    *args: str,
    env_extra: dict[str, str] | None = None,
    tty: str | None = None,
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    quoted = " ".join(shlex.quote(a) for a in args)
    extra = dict(BASE)
    extra.update(env_extra or {})
    path = "%s:%s" % (bindir, os.environ.get("PATH", "/usr/bin:/bin"))
    old_env = diff.env_for(**extra, PATH=path)
    new_env = diff.env_for(**extra, PATH=path, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s %s" % (TWIN, quoted), env=old_env, tty=tty, timeout=30)
    new = diff.bash_streams("python3 -m %s %s" % (MODULE, quoted), env=new_env, tty=tty, timeout=30)
    return old, new


def assert_identical(
    bindir: pathlib.Path,
    *args: str,
    expect_exit: int,
    env_extra: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    old, new = run_both(bindir, *args, env_extra=env_extra)
    assert old[0] == expect_exit, "twin exit changed: %r" % (old,)
    assert new[0] == old[0], "exit: %r vs %r" % (new, old)
    assert new[1] == old[1], "stdout"
    assert new[2] == old[2], "stderr"
    return old


# --------------------------------------------------------------------------- The decide path ---------------------------------------------------------------------------


def test_no_merged_pr_dispatches(bindir: pathlib.Path) -> None:
    """An empty table is a direct push, and a direct push releases."""
    old = assert_identical(bindir, "--decide-only", expect_exit=0, env_extra={"FAKE_GH_STDOUT": ""})
    assert old[1] == "decision: release\n"
    assert old[2] == (
        "✓ no merged PR contains abcdef1 (direct push, or the API knows of none); dispatching\n"
    )


def test_whitespace_only_rows_count_as_empty(bindir: pathlib.Path) -> None:
    """`${rows//[[:space:]]/}`, not `-z`: a table of blanks is still no table."""
    old = assert_identical(
        bindir, "--decide-only", expect_exit=0, env_extra={"FAKE_GH_STDOUT": "   \t  "}
    )
    assert "no merged PR contains abcdef1" in old[2]


def test_a_single_bump_none_pr_skips_the_whole_release(bindir: pathlib.Path) -> None:
    old = assert_identical(
        bindir,
        "--decide-only",
        expect_exit=0,
        env_extra={"FAKE_GH_STDOUT": "570 bump-none,documentation"},
    )
    assert old[1] == (
        "::notice title=Release skipped::#570 is labelled bump-none, so abcdef1 earns no "
        "release: no tag, no GitHub release, no R2 upload, no edge deploy. Its commits "
        "ship with the next release-worthy merge.\n"
        "decision: skip\n"
    )
    assert old[2] == "✓ release SKIPPED: #570 carries 'bump-none'\n"


def test_one_labelled_and_one_not_still_releases(bindir: pathlib.Path) -> None:
    """The asymmetry the twin's header argues for: the skip needs EVERY PR."""
    old = assert_identical(
        bindir,
        "--decide-only",
        expect_exit=0,
        env_extra={"FAKE_GH_STDOUT": "570 bump-none\n571 feature"},
    )
    assert old[1].endswith("decision: release\n")
    assert "#570 is labelled bump-none, but #571 also contains abcdef1" in old[1]


def test_the_keep_prs_trailing_space_is_defect_b(bindir: pathlib.Path) -> None:
    """`${keep_prs:-no PR}` is not `${keep_prs% }`, so the space prints."""
    old = assert_identical(
        bindir, "--decide-only", expect_exit=0, env_extra={"FAKE_GH_STDOUT": "571 feature"}
    )
    assert "✓ dispatching cd-v2 for abcdef1 (#571 )\n" in old[2]
    old = assert_identical(
        bindir,
        "--decide-only",
        expect_exit=0,
        env_extra={"FAKE_GH_STDOUT": "571 feature\n572 chore"},
    )
    assert "✓ dispatching cd-v2 for abcdef1 (#571 #572 )\n" in old[2]


def test_two_labelled_prs_and_nothing_else_skip(bindir: pathlib.Path) -> None:
    old = assert_identical(
        bindir,
        "--decide-only",
        expect_exit=0,
        env_extra={"FAKE_GH_STDOUT": "570 bump-none\n571 x,bump-none,y"},
    )
    assert old[2] == "✓ release SKIPPED: #570 #571 carries 'bump-none'\n"


def test_the_label_match_is_whole_field_not_substring(bindir: pathlib.Path) -> None:
    """`grep -qx`: `bump-none-really` and `no-bump-none` are not the label."""
    for labels in ("bump-none-really", "no-bump-none", "bump none", ""):
        old = assert_identical(
            bindir,
            "--decide-only",
            expect_exit=0,
            env_extra={"FAKE_GH_STDOUT": "570 %s" % labels},
        )
        assert old[1] == "decision: release\n", labels


def test_a_lookup_failure_fails_open(bindir: pathlib.Path) -> None:
    old = assert_identical(
        bindir,
        "--decide-only",
        expect_exit=0,
        env_extra={"FAKE_GH_RC": "1", "FAKE_GH_STDERR": "HTTP 403: Forbidden"},
    )
    assert old[1] == (
        "::notice title=Release::PR lookup failed for abcdef1; releasing rather than "
        "risking a silently withheld release.\n"
        "decision: release\n"
    )
    assert old[2] == (
        "⚠ could not resolve the PR for abcdef1 (HTTP 403: Forbidden); "
        "dispatching the release anyway\n"
    )


def test_defect_a_a_succeeding_lookups_stderr_becomes_a_phantom_pr(
    bindir: pathlib.Path,
) -> None:
    """One benign diagnostic flips skip into release, on BOTH sides.

    This is the case the `2>&1` capture makes possible, and it is asserted against the twin as well as the port so that the port is not "fixed" into disagreeing with the thing it replaces.
    """
    assert port.STDERR_IS_DATA is True
    control = assert_identical(
        bindir,
        "--decide-only",
        expect_exit=0,
        env_extra={"FAKE_GH_STDOUT": "570 bump-none"},
    )
    assert control[1].endswith("decision: skip\n")

    polluted = assert_identical(
        bindir,
        "--decide-only",
        expect_exit=0,
        env_extra={
            "FAKE_GH_STDOUT": "570 bump-none",
            "FAKE_GH_STDERR": "Warning: your gh version is out of date",
        },
    )
    assert polluted[1].endswith("decision: release\n")
    assert "#Warning: also contains abcdef1" in polluted[1]


def test_the_fakes_own_call_line_is_the_same_pollution(bindir: pathlib.Path) -> None:
    """With FAKE_GH_ECHO=stderr the recording line itself becomes a row.

    Kept as a case rather than merely avoided, because it is the proof that
    `FAKE_GH_ECHO=none` is load-bearing and not decoration.
    """
    old = assert_identical(
        bindir,
        "--decide-only",
        expect_exit=0,
        env_extra={"FAKE_GH_ECHO": "stderr", "FAKE_GH_STDOUT": "570 bump-none"},
    )
    assert "#call: " in old[2]


# --------------------------------------------------------------------------- The three modes ---------------------------------------------------------------------------


def test_dispatch_only_never_looks_anything_up(bindir: pathlib.Path) -> None:
    """No `gh api` call at all: the only recorded call is the workflow run."""
    old = assert_identical(
        bindir,
        "--dispatch-only",
        expect_exit=0,
        env_extra={"FAKE_GH_ECHO": "stderr", "GITHUB_RUN_ID": "42"},
    )
    assert old[1] == "decision: release\n"
    assert old[2] == (
        "call: gh workflow run cd-v2.yml --ref main -f release_mode=patch -f ci_run_id=42\n"
    )
    assert "gh api" not in old[2]


def test_full_mode_dispatches_after_deciding_to_release(bindir: pathlib.Path) -> None:
    old = assert_identical(
        bindir,
        expect_exit=0,
        env_extra={
            "FAKE_GH_ECHO": "dispatch",
            "FAKE_GH_STDOUT": "571 feature",
            "GITHUB_RUN_ID": "7",
        },
    )
    assert "call: gh workflow run cd-v2.yml" in old[2]
    assert old[1] == "decision: release\n"


def test_full_mode_does_not_dispatch_on_skip(bindir: pathlib.Path) -> None:
    old = assert_identical(
        bindir,
        expect_exit=0,
        env_extra={"FAKE_GH_ECHO": "dispatch", "FAKE_GH_STDOUT": "570 bump-none"},
    )
    assert "workflow run" not in old[2]
    assert old[1].endswith("decision: skip\n")


def test_the_dry_run_seam_prints_the_command_instead_of_running_it(
    bindir: pathlib.Path,
) -> None:
    old = assert_identical(
        bindir,
        expect_exit=0,
        env_extra={
            "FAKE_GH_ECHO": "dispatch",
            "FAKE_GH_STDOUT": "571 feature",
            "GITHUB_RUN_ID": "999",
            "DISPATCH_RELEASE_DRY_RUN": "1",
        },
    )
    assert old[1] == (
        "decision: release\n"
        "DRY-RUN: gh workflow run cd-v2.yml --ref main -f release_mode=patch -f ci_run_id=999\n"
    )
    assert "workflow run" not in old[2]


def test_the_dry_run_seam_is_non_emptiness_not_truth(bindir: pathlib.Path) -> None:
    """`[[ -n "${DISPATCH_RELEASE_DRY_RUN:-}" ]]`, so `false` still dry-runs."""
    old = assert_identical(
        bindir,
        "--dispatch-only",
        expect_exit=0,
        env_extra={"FAKE_GH_ECHO": "stderr", "DISPATCH_RELEASE_DRY_RUN": "false"},
    )
    assert old[1].startswith("decision: release\nDRY-RUN: ")


def test_an_absent_run_id_dispatches_with_an_empty_ci_run_id(bindir: pathlib.Path) -> None:
    """`${GITHUB_RUN_ID:-}` -- the twin does not require it."""
    old = assert_identical(
        bindir,
        "--dispatch-only",
        expect_exit=0,
        env_extra={"FAKE_GH_ECHO": "stderr", "DISPATCH_RELEASE_DRY_RUN": "1"},
    )
    assert old[1].endswith("-f ci_run_id=\n")


def test_decide_only_writes_skip_release_to_github_output(
    bindir: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """And writes NOTHING there on any other outcome, including fail-open."""
    old_out = tmp_path / "old.txt"
    new_out = tmp_path / "new.txt"
    path = "%s:%s" % (bindir, os.environ.get("PATH", "/usr/bin:/bin"))

    def drive(github_output: pathlib.Path, cmd: str, stdout: str) -> tuple[int, str, str]:
        env = diff.env_for(
            **BASE,
            FAKE_GH_STDOUT=stdout,
            PATH=path,
            GITHUB_OUTPUT=str(github_output),
            PYTHONPATH=".ci",
            PYTHONDONTWRITEBYTECODE="1",
        )
        return diff.bash_streams(cmd, env=env, timeout=30)

    drive(old_out, "bash %s --decide-only" % TWIN, "570 bump-none")
    drive(new_out, "python3 -m %s --decide-only" % MODULE, "570 bump-none")
    assert old_out.read_text(encoding="utf-8") == "skip_release=true\n"
    assert new_out.read_text(encoding="utf-8") == old_out.read_text(encoding="utf-8")

    old_out.write_text("", encoding="utf-8")
    new_out.write_text("", encoding="utf-8")
    drive(old_out, "bash %s --decide-only" % TWIN, "571 feature")
    drive(new_out, "python3 -m %s --decide-only" % MODULE, "571 feature")
    assert old_out.read_text(encoding="utf-8") == ""
    assert new_out.read_text(encoding="utf-8") == ""


def test_a_fail_open_path_writes_nothing_to_github_output(
    bindir: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """The three fail-open paths all end in a release, so none may mark a skip."""
    path = "%s:%s" % (bindir, os.environ.get("PATH", "/usr/bin:/bin"))
    for label, cmd in (
        ("old", "bash %s --decide-only" % TWIN),
        ("new", "python3 -m %s --decide-only" % MODULE),
    ):
        target = tmp_path / ("failopen-%s.txt" % label)
        env = diff.env_for(
            **BASE,
            FAKE_GH_RC="1",
            FAKE_GH_STDERR="boom",
            PATH=path,
            GITHUB_OUTPUT=str(target),
            PYTHONPATH=".ci",
            PYTHONDONTWRITEBYTECODE="1",
        )
        exit_code, _out, _err = diff.bash_streams(cmd, env=env, timeout=30)
        assert exit_code == 0
        assert not target.exists() or target.read_text(encoding="utf-8") == ""


def test_decide_only_without_github_output_still_prints_the_decision(
    bindir: pathlib.Path,
) -> None:
    """`[[ -n "${GITHUB_OUTPUT:-}" ]]`, so the stdout line is the assertable one."""
    old = assert_identical(
        bindir,
        "--decide-only",
        expect_exit=0,
        env_extra={"FAKE_GH_STDOUT": "570 bump-none"},
    )
    assert old[1].endswith("decision: skip\n")


# --------------------------------------------------------------------------- Refusals ---------------------------------------------------------------------------


def test_an_unknown_argument_exits_2(bindir: pathlib.Path) -> None:
    old = assert_identical(bindir, "--bogus", expect_exit=2)
    assert old[1] == ""
    assert old[2] == (
        "✗ unknown argument '--bogus' (expected --decide-only, --dispatch-only, or no argument)\n"
    )


def test_an_empty_first_argument_is_full_mode_not_an_error(bindir: pathlib.Path) -> None:
    """`case "${1:-}" in '')` -- an empty string is the no-flag arm."""
    old = assert_identical(
        bindir,
        "",
        expect_exit=0,
        env_extra={"FAKE_GH_STDOUT": "570 bump-none"},
    )
    assert old[1].endswith("decision: skip\n")


def test_extra_arguments_after_a_known_mode_are_ignored(bindir: pathlib.Path) -> None:
    """Only `$1` is inspected, so a typo'd SECOND flag is accepted in silence."""
    assert_identical(
        bindir,
        "--decide-only",
        "--bogus",
        expect_exit=0,
        env_extra={"FAKE_GH_STDOUT": "571 feature"},
    )


@pytest.mark.parametrize("missing", ["GITHUB_REPOSITORY", "GITHUB_SHA"])
def test_a_missing_required_variable_exits_1(bindir: pathlib.Path, missing: str) -> None:
    old = assert_identical(bindir, "--decide-only", expect_exit=1, env_extra={missing: ""})
    assert old[1] == ""
    assert old[2] == "✗ Required environment variable '%s' is not set\n" % missing


def test_both_missing_names_the_repository_first(bindir: pathlib.Path) -> None:
    """REQUIRED_VARS order is load-bearing; the twin never reaches the second."""
    assert port.REQUIRED_VARS == ("GITHUB_REPOSITORY", "GITHUB_SHA")
    old = assert_identical(
        bindir,
        "--decide-only",
        expect_exit=1,
        env_extra={"GITHUB_REPOSITORY": "", "GITHUB_SHA": ""},
    )
    assert old[2] == "✗ Required environment variable 'GITHUB_REPOSITORY' is not set\n"


def test_the_required_variables_are_checked_in_dispatch_only_mode_too(
    bindir: pathlib.Path,
) -> None:
    assert_identical(bindir, "--dispatch-only", expect_exit=1, env_extra={"GITHUB_SHA": ""})


def test_a_short_sha_is_not_padded(bindir: pathlib.Path) -> None:
    """`${GITHUB_SHA:0:7}` is a substring, so a 4-character sha stays 4."""
    old = assert_identical(
        bindir,
        "--decide-only",
        expect_exit=0,
        env_extra={"GITHUB_SHA": "abcd", "FAKE_GH_STDOUT": ""},
    )
    assert "no merged PR contains abcd (" in old[2]


def test_a_failing_dispatch_propagates_ghs_exit_status(bindir: pathlib.Path) -> None:
    """`set -e` on the last command of the case arm."""
    old, new = run_both(
        bindir,
        "--dispatch-only",
        env_extra={
            "FAKE_GH_ECHO": "dispatch",
            "FAKE_GH_RUN_RC": "3",
            "FAKE_GH_RUN_STDERR": "denied",
        },
    )
    assert old[0] == 3
    assert new[0] == old[0]
    assert new[1] == old[1]
    assert new[2] == old[2]


# --------------------------------------------------------------------------- Colour, and the pinned constants ---------------------------------------------------------------------------


def test_colour_on_a_terminal_is_byte_identical(bindir: pathlib.Path) -> None:
    old, new = run_both(
        bindir,
        "--decide-only",
        env_extra={"GITHUB_REPOSITORY": ""},
        tty="stderr",
    )
    assert old[0] == new[0] == 1
    assert diff.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert new[2] == old[2]


def test_the_warn_glyph_is_byte_identical_on_a_terminal(bindir: pathlib.Path) -> None:
    old, new = run_both(
        bindir,
        "--decide-only",
        env_extra={"FAKE_GH_RC": "1", "FAKE_GH_STDERR": "boom"},
        tty="stderr",
    )
    assert old[0] == new[0] == 0
    assert diff.escape_bytes(old[2]) > 0
    assert new[2] == old[2]


def test_no_color_suppresses_colour_on_both_sides(bindir: pathlib.Path) -> None:
    old, new = run_both(
        bindir,
        "--decide-only",
        env_extra={"GITHUB_REPOSITORY": "", "NO_COLOR": "1"},
        tty="stderr",
    )
    assert diff.escape_bytes(old[2]) == 0
    assert new[2] == old[2]


def test_the_jq_filter_is_the_twins_filter_verbatim() -> None:
    """A reworded filter would silently change WHICH PRs the decision sees."""
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        text = fh.read()
    assert "--jq '%s'" % port.PULLS_JQ in text


def test_the_skip_label_and_the_modes_are_the_twins() -> None:
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        text = fh.read()
    assert "SKIP_LABEL='%s'" % port.SKIP_LABEL in text
    for flag in ("--decide-only", "--dispatch-only"):
        assert "    %s) MODE=" % flag in text
    assert set(port.MODES) == {"", "--decide-only", "--dispatch-only"}


def test_the_endpoint_is_commits_sha_pulls_not_a_search() -> None:
    """`commits/{sha}/pulls` follows rebased commits; a search query does not."""
    assert port.pulls_url("o/r", "deadbeef") == "repos/o/r/commits/deadbeef/pulls"
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        assert "repos/${GITHUB_REPOSITORY}/commits/${GITHUB_SHA}/pulls" in fh.read()


def test_the_helpers_are_exercised_directly() -> None:
    """Both directions, so the parser cannot be trivially always-true."""
    assert port.parse_row("570 a,b") == ("570", "a,b")
    assert port.parse_row("570") == ("570", "")
    assert port.parse_row("570  a") == ("570", " a")
    assert port.has_skip_label("x,bump-none,y") is True
    assert port.has_skip_label("bump-none") is True
    assert port.has_skip_label("bump-none-really") is False
    assert port.has_skip_label("") is False
    assert port.short_sha("abcdefghij") == "abcdefg"
    assert port.short_sha("ab") == "ab"


def test_the_module_runs_as_python_m(bindir: pathlib.Path) -> None:
    """The invocation the ledger records, proven to exist.

    A module reachable only through an import in this file would pass every
    case above and still be unrunnable from the command line, which is how the
    ledger's `new` side would be measuring nothing.
    """
    env = diff.env_for(
        **BASE,
        PATH="%s:%s" % (bindir, os.environ.get("PATH", "/usr/bin:/bin")),
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    code, out, err = diff.bash_streams(
        "%s -m %s --decide-only" % (sys.executable, MODULE), env=env, timeout=30
    )
    assert code == 0
    assert out == "decision: release\n"
    assert "Traceback" not in err
