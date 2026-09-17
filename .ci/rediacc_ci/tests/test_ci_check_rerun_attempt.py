"""`rediacc_ci.ci.check_rerun_attempt` against its bash twin.

THE FAKE `gh` IS RECORDING, AND THAT IS NOT DECORATION. The twin's only input
besides the environment is one `gh api ... --jq '.run_attempt'` call, so a
differential that only compared the two scripts' log lines would pass a port
that asked for the wrong run, the wrong repository, or piped the body through a
different filter. The fake appends its exact argv to `$FAKE_LOG`, both sides
write into their OWN log, and every case asserts the two logs are identical.

WHAT IS NORMALISED, AND ONLY THIS. Three of the twin's five exits are bash's own
diagnostics (`${RUN_ID:?}`, `${GH_REPO:?}` and the `null` arithmetic), and they
begin `<program>: line <N>:`. The program NAME necessarily differs -- bash
prints the `.sh` path, Python prints the module file -- so `strip_prog` replaces
exactly that leading token with `<prog>` and compares everything after it,
INCLUDING the line number, which is the part that would silently drift.

The K=5 ledger is `.ci/shadow/w7p6-check-rerun-attempt.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-check-rerun-attempt --assert
--k 5`).
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

TWIN = ".ci/scripts/ci/check-rerun-attempt.sh"
MODULE = "rediacc_ci.ci.check_rerun_attempt"

# `<anything>: line <N>: ` at the start of a line. The path is the program name and is the only token allowed to differ between the two sides.
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
    """Replace the leading `<program>:` of a bash diagnostic with `<prog>:`."""
    return _PROG.sub("<prog>: line ", text)


def make_fakebin(tmp_path: pathlib.Path, *, with_gh: bool = True) -> pathlib.Path:
    """A PATH directory holding the fake `gh` and the tools common.sh needs.

    `with_gh=False` is how the missing-tool arm is reached: `gh` really is
    installed at /usr/bin/gh on this machine, so the only honest way to test
    `require_cmd gh` refusing is a PATH that does not contain /usr/bin at all.
    `uname` is symlinked in because common.sh computes CI_OS/CI_ARCH at SOURCE
    time and would otherwise fail for a reason unrelated to the case.
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


def run_both(
    tmp_path: pathlib.Path,
    *,
    env_extra: dict[str, str] | None = None,
    with_gh: bool = True,
    github_env: bool = True,
    tty: str | None = None,
) -> tuple[tuple[int, str, str], tuple[int, str, str], dict[str, str]]:
    """Drive both sides through their own fake-gh call log and GITHUB_ENV file.

    Returns the two `(exit, stdout, stderr)` triples plus a dict of the
    side-effect files, so a caller can assert on the call log and the exported
    variable without re-deriving the paths.
    """
    bindir = make_fakebin(tmp_path, with_gh=with_gh)
    path = str(bindir) if not with_gh else "%s:%s" % (bindir, os.environ.get("PATH", ""))

    files = {}
    per_side = {}
    for side in ("old", "new"):
        log = tmp_path / ("%s-ghcalls.txt" % side)
        log.write_text("", encoding="utf-8")
        env = dict(env_extra or {})
        env["FAKE_LOG"] = str(log)
        env["PATH"] = path
        if github_env:
            envfile = tmp_path / ("%s-github-env.txt" % side)
            envfile.write_text("", encoding="utf-8")
            env["GITHUB_ENV"] = str(envfile)
            files["%s_envfile" % side] = envfile
        per_side[side] = env
        files["%s_log" % side] = log

    old = diff.bash_streams(
        "bash %s" % TWIN, env=diff.env_for(**per_side["old"]), tty=tty, timeout=30
    )
    new = diff.bash_streams(
        "python3 -m %s" % MODULE,
        env=diff.env_for(**per_side["new"], PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1"),
        tty=tty,
        timeout=30,
    )
    read = {k: v.read_text(encoding="utf-8") if v.exists() else None for k, v in files.items()}
    return old, new, read


def assert_identical(old, new, files) -> None:
    assert new[0] == old[0], "exit code: %r vs %r" % (old, new)
    assert new[1] == old[1], "stdout: %r vs %r" % (old[1], new[1])
    assert strip_prog(new[2]) == strip_prog(old[2]), "stderr: %r vs %r" % (old[2], new[2])
    assert files["new_log"] == files["old_log"], "gh call log diverged"
    if "old_envfile" in files:
        assert files["new_envfile"] == files["old_envfile"], "GITHUB_ENV diverged"


def test_below_the_cap_allows_the_rerun_and_exports_false(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "rediacc/console"})
    assert old[0] == 0
    assert old[1] == "::group::Fetching run details\n::endgroup::\n"
    assert "Run attempt 1 < max 2 - rerun is allowed" in old[2]
    assert files["old_envfile"] == "WATCHDOG_SKIP_RERUN=false\n"
    assert (
        files["old_log"] == "FAKEGH| api repos/rediacc/console/actions/runs/5 --jq .run_attempt\n"
    )
    assert_identical(old, new, files)


def test_at_the_cap_skips_the_rerun_and_exports_true(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": "2"}
    )
    assert old[0] == 0
    assert "⚠ Run attempt 2 >= max 2 - skipping rerun (defense-in-depth)" in old[2]
    assert files["old_envfile"] == "WATCHDOG_SKIP_RERUN=true\n"
    assert_identical(old, new, files)


def test_past_the_cap_skips_too(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": "7"}
    )
    assert files["old_envfile"] == "WATCHDOG_SKIP_RERUN=true\n"
    assert_identical(old, new, files)


def test_max_attempts_is_overridable_and_the_default_is_two(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path,
        env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": "3", "MAX_ATTEMPTS": "9"},
    )
    assert "Run attempt 3 < max 9" in old[2]
    assert files["old_envfile"] == "WATCHDOG_SKIP_RERUN=false\n"
    assert_identical(old, new, files)
    assert port.DEFAULT_MAX_ATTEMPTS == "2"


def test_an_empty_max_attempts_falls_back_to_two(tmp_path: pathlib.Path) -> None:
    """`${MAX_ATTEMPTS:-2}` is an EMPTINESS test, not a presence test."""
    old, new, files = run_both(
        tmp_path,
        env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": "2", "MAX_ATTEMPTS": ""},
    )
    assert "Run attempt 2 >= max 2" in old[2]
    assert_identical(old, new, files)


def test_defect_a_an_unset_github_env_makes_the_happy_path_exit_1(
    tmp_path: pathlib.Path,
) -> None:
    """The twin ends on `[[ -n "$GITHUB_ENV" ]] && echo ...`, so a false test IS the exit.

    `GITHUB_ENV` is OPTIONAL by the twin's own header, and leaving it out turns
    a run that printed "rerun is allowed" into a failure with no failing
    message. Pinned in BOTH directions in one test: identical output, exit 1
    without the variable and exit 0 with it.
    """
    old, new, files = run_both(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b"}, github_env=False
    )
    assert old[0] == 1, "the twin's DEFECT A changed; re-read the module docstring"
    assert "✓ Run attempt 1 < max 2 - rerun is allowed" in old[2]
    assert "✗" not in old[2], "it exits 1 having printed no error at all"
    assert_identical(old, new, files)

    with_env = run_both(tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b"})
    assert with_env[0][0] == 0
    assert with_env[0][2] == old[2], "the only difference is the exit code"


def test_defect_b_an_empty_attempt_fails_open(tmp_path: pathlib.Path) -> None:
    """Empty is arithmetic 0, so the cap reads as not reached. Wrong direction."""
    old, new, files = run_both(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": ""}
    )
    assert old[0] == 0
    assert "Run attempt  < max 2 - rerun is allowed" in old[2]
    assert files["old_envfile"] == "WATCHDOG_SKIP_RERUN=false\n"
    assert_identical(old, new, files)


def test_defect_b_a_null_attempt_fails_closed_with_an_unreadable_message(
    tmp_path: pathlib.Path,
) -> None:
    """`jq -r` prints `null` for a missing key; bash reads it as a variable name."""
    old, new, files = run_both(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": "null"}
    )
    assert old[0] == 1
    assert strip_prog(old[2]).endswith("<prog>: line 40: null: unbound variable\n")
    assert files["old_envfile"] == "", "it dies before writing WATCHDOG_SKIP_RERUN"
    assert_identical(old, new, files)


def test_a_failing_gh_propagates_its_status_and_leaves_the_group_unclosed(
    tmp_path: pathlib.Path,
) -> None:
    """`::endgroup::` is never printed on this path, which is observable output."""
    old, new, files = run_both(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_GH_RC": "4"}
    )
    assert old[0] == 4
    assert old[1] == "::group::Fetching run details\n"
    assert "::endgroup::" not in old[1]
    assert_identical(old, new, files)


def test_a_missing_run_id_is_bashs_own_diagnostic_at_line_29(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(tmp_path, env_extra={"GH_REPO": "a/b"})
    assert old[0] == 1
    assert strip_prog(old[2]) == "<prog>: line 29: RUN_ID: RUN_ID is required\n"
    assert old[1] == ""
    assert files["old_log"] == "", "it refuses before calling gh"
    assert_identical(old, new, files)


def test_an_empty_run_id_refuses_exactly_like_a_missing_one(tmp_path: pathlib.Path) -> None:
    """`${RUN_ID:?}` is `:?`, an emptiness test, not `?`."""
    old, new, files = run_both(tmp_path, env_extra={"RUN_ID": "", "GH_REPO": "a/b"})
    assert strip_prog(old[2]) == "<prog>: line 29: RUN_ID: RUN_ID is required\n"
    assert_identical(old, new, files)


def test_a_missing_gh_repo_is_refused_at_line_30(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(tmp_path, env_extra={"RUN_ID": "5"})
    assert old[0] == 1
    assert strip_prog(old[2]) == "<prog>: line 30: GH_REPO: GH_REPO is required\n"
    assert_identical(old, new, files)


def test_run_id_is_checked_before_gh_repo(tmp_path: pathlib.Path) -> None:
    """Both missing: one message, and it is RUN_ID's. Order is the contract."""
    old, new, files = run_both(tmp_path, env_extra={})
    assert strip_prog(old[2]) == "<prog>: line 29: RUN_ID: RUN_ID is required\n"
    assert_identical(old, new, files)


def test_a_missing_gh_is_a_named_refusal_on_both_sides(tmp_path: pathlib.Path) -> None:
    """`require_cmd gh` before anything else, and it must not read as a pass."""
    old, new, files = run_both(tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b"}, with_gh=False)
    assert old[0] == 1
    assert old[2] == "✗ Required command 'gh' is not available\n"
    assert old[1] == ""
    assert_identical(old, new, files)


def test_the_pinned_line_numbers_still_point_at_the_twins_lines() -> None:
    """The three constants are bash's line numbers, so they must be re-derived.

    A paragraph inserted above any of them moves it, and every diagnostic this
    port prints would then name a line that says something else. Re-read the
    twin rather than trust the constants.
    """
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    assert lines[port.RUN_ID_LINE - 1].strip() == ': "${RUN_ID:?RUN_ID is required}"'
    assert lines[port.GH_REPO_LINE - 1].strip() == ': "${GH_REPO:?GH_REPO is required}"'
    assert lines[port.ARITH_LINE - 1].strip() == 'if [[ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]]; then'


def test_the_exported_variable_name_is_the_consumers_spelling() -> None:
    """The twin's header says the name is spelled once. Prove it is still one."""
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        text = fh.read()
    assert 'echo "%s=${SKIP}"' % port.SKIP_VAR in text


def test_colour_on_a_terminal_is_byte_identical(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "FAKE_ATTEMPT": "2"}, tty="stderr"
    )
    assert diff.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert_identical(old, new, files)


def test_no_color_suppresses_colour_on_both_sides(tmp_path: pathlib.Path) -> None:
    old, new, files = run_both(
        tmp_path,
        env_extra={"RUN_ID": "5", "GH_REPO": "a/b", "NO_COLOR": "1"},
        tty="stderr",
    )
    assert diff.escape_bytes(old[2]) == 0
    assert_identical(old, new, files)


def test_the_group_directives_are_on_stdout_and_the_log_lines_on_stderr(
    tmp_path: pathlib.Path,
) -> None:
    """A stream swap is the one defect a merged `2>&1` comparison cannot see."""
    old, new, files = run_both(tmp_path, env_extra={"RUN_ID": "5", "GH_REPO": "a/b"})
    assert old[1].splitlines() == ["::group::Fetching run details", "::endgroup::"]
    assert "::group::" not in old[2]
    assert "Run ID: 5" not in old[1]
    assert_identical(old, new, files)
