"""`rediacc_ci.ci.check_rerun_attempt`, driven directly.

THE FAKE `gh` IS RECORDING, AND THAT IS NOT DECORATION. The subject's only input besides the environment is one `gh api ... --jq '.run_attempt'` call, so a suite that only read the log lines would pass a gate that asked for the wrong run, the wrong repository, or piped the body through a different filter. The fake appends its exact argv to `$FAKE_LOG` and the cases assert that
log.

WHILE BOTH COPIES EXISTED each case ran `.ci/scripts/ci/check-rerun-attempt.sh` beside the port over the same fake, comparing exit code, stdout, stderr, the call log and the `$GITHUB_ENV` file. Three of the five exits are bash's own diagnostics, carrying `<program>: line <N>:`, and only the program NAME was normalised away; the line numbers were compared. Those numbers are now
frozen archaeology, pinned as constants on the port and asserted below against the port's own output rather than re-derived from a file that no longer exists.

The K=5 ledger `.ci/shadow/w7p6-check-rerun-attempt.observations.jsonl` recorded the verdict over nine distinct trees (`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-check-rerun-attempt --assert --k 5`) and licensed the port; W7 P5 retired the twin and the cases that executed it went with it.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import sys
from typing import TYPE_CHECKING

from rediacc_ci.ci import check_rerun_attempt as port
from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

MODULE = "rediacc_ci.ci.check_rerun_attempt"

# `<anything>: line <N>: ` at the start of a line. The program name is the one token the twin and the port were ever allowed to spell differently.
_PROG = re.compile(r"^\S+: line ", re.MULTILINE)

FAKE_GH_SRC = """#!{python}
import os
import sys

argv = sys.argv[1:]
log = os.environ.get("FAKE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("FAKEGH| " + " ".join(argv) + "\\n")
rc = int(os.environ.get("FAKE_GH_RC", "0"))
if rc != 0:
    sys.stderr.write("gh: simulated failure\\n")
    sys.exit(rc)
sys.stdout.write(os.environ.get("FAKE_ATTEMPT", "1") + "\\n")
"""


def strip_prog(text: str) -> str:
    """Replace the leading `<program>:` of a bash-shaped diagnostic with `<prog>:`."""
    return _PROG.sub("<prog>: line ", text)


def make_fakebin(tmp_path: pathlib.Path, *, with_gh: bool = True) -> pathlib.Path:
    """A PATH directory holding the fake `gh` and the tools the subject needs.

    `with_gh=False` is how the missing-tool arm is reached: `gh` really is
    installed at /usr/bin/gh on this machine, so the only honest way to test `require_cmd gh` refusing is a PATH that does not contain /usr/bin at all. `uname` is symlinked in because the common library computes CI_OS/CI_ARCH at import time and would otherwise fail for a reason unrelated to the case.
    """
    bindir = tmp_path / ("fakebin-gh" if with_gh else "fakebin-nogh")
    bindir.mkdir(exist_ok=True)
    for tool in ("bash", "python3", "uname", "dirname", "cat", "sed", "date"):
        found = shutil.which(tool)
        target = bindir / tool
        if found and not target.exists():
            target.symlink_to(found)
    script = bindir / "gh"
    if with_gh:
        script.write_text(FAKE_GH_SRC.format(python=sys.executable), encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def run_port(
    tmp_path: pathlib.Path,
    *,
    env_extra: dict[str, str] | None = None,
    with_gh: bool = True,
    github_env: bool = True,
    tty: str | None = None,
    label: str = "run",
) -> tuple[tuple[int, str, str], dict[str, str | None]]:
    """Drive the port through its own fake-gh call log and GITHUB_ENV file.

    Returns the `(exit, stdout, stderr)` triple plus a dict of the side-effect files, so a caller can assert on the call log and the exported variable without re-deriving the paths.
    """
    bindir = make_fakebin(tmp_path, with_gh=with_gh)
    path = str(bindir) if not with_gh else "%s:%s" % (bindir, os.environ.get("PATH", ""))

    log = tmp_path / ("%s-ghcalls.txt" % label)
    log.write_text("", encoding="utf-8")
    env = dict(env_extra or {})
    env["FAKE_LOG"] = str(log)
    env["PATH"] = path
    files = {"log": log}
    if github_env:
        envfile = tmp_path / ("%s-github-env.txt" % label)
        envfile.write_text("", encoding="utf-8")
        env["GITHUB_ENV"] = str(envfile)
        files["envfile"] = envfile

    result = diff.bash_streams(
        "python3 -m %s" % MODULE,
        env=diff.env_for(**env, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"),
        tty=tty,
        timeout=30,
    )
    read = {k: v.read_text(encoding="utf-8") if v.exists() else None for k, v in files.items()}
    return result, read


def test_below_the_cap_allows_the_rerun_and_exports_false(tmp_path: pathlib.Path) -> None:
    result, files = run_port(tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "rediacc/console"})
    assert result[0] == 0
    assert result[1] == "::group::Fetching run details\n::endgroup::\n"
    assert "Run attempt 1 < max 2 - rerun is allowed" in result[2]
    assert files["envfile"] == "WATCHDOG_SKIP_RERUN=false\n"
    assert files["log"] == "FAKEGH| api repos/rediacc/console/actions/runs/5 --jq .run_attempt\n"


def test_at_the_cap_skips_the_rerun_and_exports_true(tmp_path: pathlib.Path) -> None:
    result, files = run_port(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": "2"}
    )
    assert result[0] == 0
    assert "⚠ Run attempt 2 >= max 2 - skipping rerun (defense-in-depth)" in result[2]
    assert files["envfile"] == "WATCHDOG_SKIP_RERUN=true\n"


def test_past_the_cap_skips_too(tmp_path: pathlib.Path) -> None:
    _, files = run_port(tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": "7"})
    assert files["envfile"] == "WATCHDOG_SKIP_RERUN=true\n"


def test_max_attempts_is_overridable_and_the_default_is_two(tmp_path: pathlib.Path) -> None:
    result, files = run_port(
        tmp_path,
        env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": "3", "MAX_ATTEMPTS": "9"},
    )
    assert "Run attempt 3 < max 9" in result[2]
    assert files["envfile"] == "WATCHDOG_SKIP_RERUN=false\n"
    assert port.DEFAULT_MAX_ATTEMPTS == "2"


def test_an_empty_max_attempts_falls_back_to_two(tmp_path: pathlib.Path) -> None:
    """`${MAX_ATTEMPTS:-2}` was an EMPTINESS test, not a presence test."""
    result, _ = run_port(
        tmp_path,
        env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": "2", "MAX_ATTEMPTS": ""},
    )
    assert "Run attempt 2 >= max 2" in result[2]


def test_defect_a_an_unset_github_env_makes_the_happy_path_exit_1(
    tmp_path: pathlib.Path,
) -> None:
    """The twin ended on `[[ -n "$GITHUB_ENV" ]] && echo ...`, so a false test WAS the exit.

    `GITHUB_ENV` is OPTIONAL by that script's own header, and leaving it out turns a run that printed "rerun is allowed" into a failure with no failing message. Pinned in BOTH directions in one test: identical output, exit 1 without the variable and exit 0 with it.
    """
    result, _ = run_port(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b"}, github_env=False, label="no-env"
    )
    assert result[0] == 1, "DEFECT A changed; re-read the port's module docstring"
    assert "✓ Run attempt 1 < max 2 - rerun is allowed" in result[2]
    assert "✗" not in result[2], "it exits 1 having printed no error at all"

    with_env, _ = run_port(tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b"}, label="with-env")
    assert with_env[0] == 0
    assert with_env[2] == result[2], "the only difference is the exit code"


def test_defect_b_an_empty_attempt_fails_open(tmp_path: pathlib.Path) -> None:
    """Empty is arithmetic 0, so the cap reads as not reached. Wrong direction."""
    result, files = run_port(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": ""}
    )
    assert result[0] == 0
    assert "Run attempt  < max 2 - rerun is allowed" in result[2]
    assert files["envfile"] == "WATCHDOG_SKIP_RERUN=false\n"


def test_defect_b_a_null_attempt_fails_closed_with_an_unreadable_message(
    tmp_path: pathlib.Path,
) -> None:
    """`jq -r` prints `null` for a missing key; bash read it as a variable name."""
    result, files = run_port(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": "null"}
    )
    assert result[0] == 1
    assert strip_prog(result[2]).endswith(
        "<prog>: line %d: null: unbound variable\n" % port.ARITH_LINE
    )
    assert files["envfile"] == "", "it dies before writing WATCHDOG_SKIP_RERUN"


def test_a_failing_gh_propagates_its_status_and_leaves_the_group_unclosed(
    tmp_path: pathlib.Path,
) -> None:
    """`::endgroup::` is never printed on this path, which is observable output."""
    result, _ = run_port(tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_GH_RC": "4"})
    assert result[0] == 4
    assert result[1] == "::group::Fetching run details\n"
    assert "::endgroup::" not in result[1]


def test_a_missing_run_id_is_the_pinned_diagnostic(tmp_path: pathlib.Path) -> None:
    result, files = run_port(tmp_path, env_extra={"GH_REPO": "a/b"})
    assert result[0] == 1
    assert (
        strip_prog(result[2]) == "<prog>: line %d: RUN_ID: RUN_ID is required\n" % port.RUN_ID_LINE
    )
    assert result[1] == ""
    assert files["log"] == "", "it refuses before calling gh"


def test_an_empty_run_id_refuses_exactly_like_a_missing_one(tmp_path: pathlib.Path) -> None:
    """`${RUN_ID:?}` was `:?`, an emptiness test, not `?`."""
    result, _ = run_port(tmp_path, env_extra={"RUN_ID": "", "GH_REPO": "a/b"})
    assert (
        strip_prog(result[2]) == "<prog>: line %d: RUN_ID: RUN_ID is required\n" % port.RUN_ID_LINE
    )


def test_a_missing_gh_repo_is_the_pinned_diagnostic(tmp_path: pathlib.Path) -> None:
    result, _ = run_port(tmp_path, env_extra={"RUN_ID": "5"})
    assert result[0] == 1
    assert (
        strip_prog(result[2])
        == "<prog>: line %d: GH_REPO: GH_REPO is required\n" % port.GH_REPO_LINE
    )


def test_run_id_is_checked_before_gh_repo(tmp_path: pathlib.Path) -> None:
    """Both missing: one message, and it is RUN_ID's. Order is the contract."""
    result, _ = run_port(tmp_path, env_extra={})
    assert (
        strip_prog(result[2]) == "<prog>: line %d: RUN_ID: RUN_ID is required\n" % port.RUN_ID_LINE
    )


def test_a_missing_gh_is_a_named_refusal(tmp_path: pathlib.Path) -> None:
    """`require_cmd gh` before anything else, and it must not read as a pass."""
    result, _ = run_port(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b"}, with_gh=False, label="no-gh"
    )
    assert result[0] == 1
    assert result[2] == "✗ Required command 'gh' is not available\n"
    assert result[1] == ""


def test_the_three_pinned_line_numbers_are_distinct_and_still_printed() -> None:
    """ANTI-VACUITY, re-aimed. The twin is gone, so the constants cannot be re-derived from it any more; what can still be asserted is that they are three separate numbers rather than one default, and the cases above assert each one reaching stderr."""
    numbers = (port.RUN_ID_LINE, port.GH_REPO_LINE, port.ARITH_LINE)
    assert len(set(numbers)) == 3
    assert all(isinstance(n, int) and n > 0 for n in numbers)


def test_the_exported_variable_name_is_the_consumers_spelling() -> None:
    """`watchdog-monitor.cjs` reads this name, so the port does not get to rename it."""
    assert port.SKIP_VAR == "WATCHDOG_SKIP_RERUN"


def test_colour_is_emitted_on_a_terminal(tmp_path: pathlib.Path) -> None:
    result, _ = run_port(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": "2"}, tty="stderr"
    )
    assert diff.escape_bytes(result[2]) > 0, "no colour was printed on a tty"


def test_no_color_suppresses_colour(tmp_path: pathlib.Path) -> None:
    result, _ = run_port(
        tmp_path,
        env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "NO_COLOR": "1"},
        tty="stderr",
    )
    assert diff.escape_bytes(result[2]) == 0


def test_the_group_directives_are_on_stdout_and_the_log_lines_on_stderr(
    tmp_path: pathlib.Path,
) -> None:
    """A stream swap is the one defect a merged `2>&1` comparison cannot see."""
    result, _ = run_port(tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b"})
    assert result[1].splitlines() == ["::group::Fetching run details", "::endgroup::"]
    assert "::group::" not in result[2]
    assert "Run ID: 5" not in result[1]
