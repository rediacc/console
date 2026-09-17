"""Differential: `rediacc_ci.housekeeping.cleanup_github_deployments` against
its twin `.ci/scripts/housekeeping/cleanup-github-deployments.sh`.

A RECORDING FAKE `gh`, written as Python, seam is PATH -- ruling 7's shape, as
in `test_pr_sync_epic_block.py`. Nothing here reaches the network, and the real
`gh` on this machine is never on the PATH handed to either subject. That is not
merely tidy: this script's non-dry-run arm DELETES deployment records, and its
`--repo` comes from the command line, so a case that leaked the real binary
would delete real records from whatever repository the argument named.

THE CALL LOG IS THE PRIMARY ARTIFACT, not stdout. This script writes NOTHING to
stdout (every message is `log_*`, which is stderr), and its whole observable
effect is the sequence of `gh` invocations. So every case compares the two
sides' recorded call sequences as well as their streams and exit codes: a port
that printed the right messages while making the wrong requests would otherwise
pass.

TWO CASES PIN DEFECTS IN THE TWIN RATHER THAN CORRECT BEHAVIOUR, and say so in
their own names, so a future fix turns them red instead of sliding past:
`test_DEFECT_failed_deletions_do_not_affect_the_exit_code` and
`test_DEFECT_the_environment_is_not_url_encoded`. Both are described in the
port's module docstring.

K=5 LEDGER: `.ci/shadow/w7p6-cleanup-github-deployments.observations.jsonl`
-- five distinct trees, `--assert --k 5` prints "equivalence holds over 5
distinct trees". Recorded in a disposable scratch repo outside this checkout
(dirty tree; `--record` refuses one) with the same fake `gh` on PATH, one
scenario per tree: a dry run over three ids, one failed deletion, all
deletions failing, a usage error, and a listing that returns HTTP 403.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.housekeeping import cleanup_github_deployments as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "housekeeping" / "cleanup-github-deployments.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "housekeeping" / "cleanup_github_deployments.py"
BASH = shutil.which("bash") or "/bin/bash"

FAKE_GH = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write("\\t".join(argv) + "\\n")

# The listing call: `api <path> --paginate --jq .[].id`.
if "--paginate" in argv:
    rc = int(os.environ.get("FAKE_GH_LIST_RC", "0"))
    if rc != 0:
        sys.stderr.write("gh: fake listing failure (HTTP 403)\\n")
        sys.exit(rc)
    ids = os.environ.get("FAKE_GH_IDS", "")
    if ids:
        sys.stdout.write(ids.replace(",", "\\n") + "\\n")
    sys.exit(0)

if "DELETE" in argv:
    deployment_id = argv[-1].rsplit("/", 1)[-1]
    fails = os.environ.get("FAKE_GH_DELETE_FAILS", "").split(",")
    sys.stdout.write("fake DELETE output that must never be seen\\n")
    sys.stderr.write("fake DELETE stderr that must never be seen\\n")
    sys.exit(1 if deployment_id in fails else 0)

# The inactive-status POST.
sys.stdout.write("fake status output that must never be seen\\n")
sys.exit(int(os.environ.get("FAKE_GH_STATUS_RC", "0")))
"""

# What the two subjects need on PATH besides the fake gh. The twin sources common.sh (`dirname` at line 15, `uname` for the CI_OS/CI_ARCH assignments at source time) and its `parse_args` calls `to_upper`, which shells out to `tr` once per flag (common.sh:301-303). Found by driving it: the first attempt omitted `tr` and every argument-parsing case died with "common.sh: line 302: tr:
# command not found", exit 127.
PATH_MINIMUM = ("dirname", "uname", "tr")


def _bin(tmp_path: pathlib.Path, name: str, *, with_gh: bool = True) -> str:
    stub = tmp_path / name
    stub.mkdir(exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    if with_gh:
        fake = stub / "gh"
        fake.write_text(FAKE_GH, encoding="utf-8")
        fake.chmod(0o755)
    else:
        assert shutil.which("gh", path=str(stub)) is None, "gh leaked into the stub PATH"
    return str(stub)


def _run(
    subject: pathlib.Path, tmp_path: pathlib.Path, args: list[str], *, with_gh: bool, **gh_env: str
):
    side = "old" if subject.suffix == ".sh" else "new"
    log = tmp_path / f"{side}-gh-calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, f"{side}-bin", with_gh=with_gh),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(log),
    }
    env.update(gh_env)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *args],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls


def run_both(tmp_path: pathlib.Path, args: list[str], *, with_gh: bool = True, **gh_env: str):
    old, old_calls = _run(TWIN, tmp_path, args, with_gh=with_gh, **gh_env)
    new, new_calls = _run(PORT, tmp_path, args, with_gh=with_gh, **gh_env)
    return old, new, old_calls, new_calls


def _assert_agree(old, new, label: str, old_calls=None, new_calls=None) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )
    if old_calls is not None:
        assert new_calls == old_calls, (
            f"{label}: gh call sequence diverged:\nold: {old_calls}\nnew: {new_calls}"
        )


LIST_CALL = (
    "api\trepos/acme/widget/deployments?environment=pr-42&per_page=100\t--paginate\t--jq\t.[].id"
)


def test_no_arguments_prints_the_usage(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    assert old.returncode == 1
    assert old.stdout == ""
    assert old.stderr == (
        "✗ Usage: cleanup-github-deployments.sh --repo <owner/repo> "
        "--environment <name> [--dry-run]\n"
    )
    assert old_calls == [], "gh was called before the arguments were validated"
    _assert_agree(old, new, "no-args", old_calls, new_calls)


def test_repo_without_environment_prints_the_usage(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--repo", "acme/widget"])
    assert old.returncode == 1
    _assert_agree(old, new, "repo-only", old_calls, new_calls)


def test_environment_without_repo_prints_the_usage(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--environment", "pr-42"])
    assert old.returncode == 1
    _assert_agree(old, new, "environment-only", old_calls, new_calls)


def test_missing_gh_refuses_before_the_usage_check(tmp_path: pathlib.Path) -> None:
    """ORDER MATTERS AND IS REPRODUCED: `require_cmd gh` runs BEFORE the
    argument validation, so a machine without gh reports the missing binary
    even when the command line is also wrong."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], with_gh=False)
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'gh' is not available\n"
    _assert_agree(old, new, "missing-gh", old_calls, new_calls)


def test_no_deployments_found(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--repo", "acme/widget", "--environment", "pr-42"], FAKE_GH_IDS=""
    )
    assert old.returncode == 0
    assert old.stdout == ""
    assert old.stderr.endswith("✓ No deployments found for pr-42\n")
    assert old_calls == [LIST_CALL]
    _assert_agree(old, new, "no-deployments", old_calls, new_calls)


def test_dry_run_deletes_nothing(tmp_path: pathlib.Path) -> None:
    """THE SAFE PATH, and the assertion that matters is the CALL LOG: exactly
    one listing call and not a single DELETE."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--repo", "acme/widget", "--environment", "pr-42", "--dry-run"],
        FAKE_GH_IDS="101,102,103",
    )
    assert old.returncode == 0
    assert "⚠ DRY-RUN mode: no deletions will be performed" in old.stderr
    assert "⚠ [DRY-RUN] Would delete deployment 101 (pr-42)" in old.stderr
    assert old.stderr.endswith("✓ Would delete 3 deployment(s) for pr-42\n")
    assert old_calls == [LIST_CALL], f"dry-run made mutating calls: {old_calls}"
    _assert_agree(old, new, "dry-run", old_calls, new_calls)


def test_real_path_marks_inactive_then_deletes_each_id(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--repo", "acme/widget", "--environment", "pr-42"],
        FAKE_GH_IDS="101,102",
    )
    assert old.returncode == 0
    assert old.stderr.endswith("✓ Deleted 2 of 2 deployment(s) for pr-42\n")
    assert old_calls == [
        LIST_CALL,
        "api\trepos/acme/widget/deployments/101/statuses\t-X\tPOST\t-f\tstate=inactive",
        "api\t-X\tDELETE\trepos/acme/widget/deployments/101",
        "api\trepos/acme/widget/deployments/102/statuses\t-X\tPOST\t-f\tstate=inactive",
        "api\t-X\tDELETE\trepos/acme/widget/deployments/102",
    ]
    _assert_agree(old, new, "real-path", old_calls, new_calls)


def test_gh_output_from_the_mutating_calls_is_swallowed(tmp_path: pathlib.Path) -> None:
    """`>/dev/null 2>&1` on BOTH mutation calls. The fake writes to both
    streams precisely so a port that forgot one would be caught here."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--repo", "acme/widget", "--environment", "pr-42"], FAKE_GH_IDS="101"
    )
    assert "must never be seen" not in old.stdout + old.stderr
    assert "must never be seen" not in new.stdout + new.stderr
    _assert_agree(old, new, "swallowed-gh-output", old_calls, new_calls)


def test_a_failed_deletion_warns_and_the_others_still_run(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--repo", "acme/widget", "--environment", "pr-42"],
        FAKE_GH_IDS="101,102,103",
        FAKE_GH_DELETE_FAILS="102",
    )
    assert "⚠ Failed to delete deployment 102 (pr-42)" in old.stderr
    assert old.stderr.endswith("✓ Deleted 2 of 3 deployment(s) for pr-42\n")
    assert any("deployments/103" in call for call in old_calls), "the loop stopped at the failure"
    _assert_agree(old, new, "one-delete-fails", old_calls, new_calls)


def test_defect_failed_deletions_do_not_affect_the_exit_code(tmp_path: pathlib.Path) -> None:
    """PINNING A DEFECT, NOT A REQUIREMENT. Every deletion fails and the script
    still exits 0, so a workflow step shows a green tick while the Deployments
    view is untouched. Reported to the driver rather than fixed here: changing
    it changes live release-path behaviour on both sides at once. If the twin
    is ever fixed, THIS TEST GOES RED, which is the point."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--repo", "acme/widget", "--environment", "pr-42"],
        FAKE_GH_IDS="101,102",
        FAKE_GH_DELETE_FAILS="101,102",
    )
    assert old.returncode == 0, "the twin now fails on a failed deletion; update this test"
    assert old.stderr.endswith("✓ Deleted 0 of 2 deployment(s) for pr-42\n")
    _assert_agree(old, new, "all-deletes-fail", old_calls, new_calls)


def test_defect_the_environment_is_not_url_encoded(tmp_path: pathlib.Path) -> None:
    """PINNING A DEFECT. An environment name carrying `&` is interpolated raw
    into the query string, so the request asks for something else entirely.
    Latent today (every caller passes `pr-<n>`), reproduced on both sides."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--repo", "acme/widget", "--environment", "pr-1&per_page=1"],
        FAKE_GH_IDS="",
    )
    assert old_calls == [
        (
            "api\trepos/acme/widget/deployments?environment=pr-1&per_page=1&per_page=100"
            "\t--paginate\t--jq\t.[].id"
        )
    ]
    _assert_agree(old, new, "unencoded-environment", old_calls, new_calls)


def test_dry_run_false_is_not_a_dry_run(tmp_path: pathlib.Path) -> None:
    """common.sh's parse_args QUIRK 2: `--dry-run false` consumes the next
    token as the VALUE, so DRY_RUN is the string `false` and the deletions are
    real. Surprising, live, and identical on both sides."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--repo", "acme/widget", "--environment", "pr-42", "--dry-run", "false"],
        FAKE_GH_IDS="101",
    )
    assert old.returncode == 0
    assert "DRY-RUN" not in old.stderr
    assert any("DELETE" in call for call in old_calls), "the twin treated it as a dry run"
    _assert_agree(old, new, "dry-run-false", old_calls, new_calls)


def test_listing_failure_propagates_with_ghs_own_stderr(tmp_path: pathlib.Path) -> None:
    """The listing is `$(gh ...)` with stderr INHERITED, so gh's diagnostic
    reaches the caller and `set -e` takes the exit code."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--repo", "acme/widget", "--environment", "pr-42"],
        FAKE_GH_LIST_RC="7",
    )
    assert old.returncode == 7
    assert "fake listing failure (HTTP 403)" in old.stderr, "the twin swallowed gh's stderr"
    _assert_agree(old, new, "listing-fails", old_calls, new_calls)


def test_nothing_is_ever_written_to_stdout(tmp_path: pathlib.Path) -> None:
    """Every message is `log_*`, which is stderr. A port that used `print()`
    for progress would look right in a terminal and corrupt a pipe."""
    old, new, _old_calls, _new_calls = run_both(
        tmp_path,
        ["--repo", "acme/widget", "--environment", "pr-42", "--dry-run"],
        FAKE_GH_IDS="101,102",
    )
    assert old.stdout == "", f"the TWIN wrote to stdout: {old.stdout!r}"
    assert new.stdout == "", f"the PORT wrote to stdout: {new.stdout!r}"
    assert old.stderr != ""


def test_pure_url_builders() -> None:
    assert port.list_path("a/b", "pr-1") == "repos/a/b/deployments?environment=pr-1&per_page=100"
    assert port.statuses_path("a/b", "9") == "repos/a/b/deployments/9/statuses"
    assert port.delete_path("a/b", "9") == "repos/a/b/deployments/9"


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the line that makes `--dry-run` safe. Removing
    the `continue` turns the dry run into a real one: the messages stay
    identical, the exit code stays 0, and only the CALL LOG shows that records
    were deleted -- which is exactly why every case in this file compares the
    call log. Driven red, then the source is restored byte-identical and
    re-verified green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        '            log.warn("[DRY-RUN] Would delete deployment %s (%s)" '
        "% (deployment_id, environment))\n            continue\n",
        '            log.warn("[DRY-RUN] Would delete deployment %s (%s)" '
        "% (deployment_id, environment))\n",
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    args = ["--repo", "acme/widget", "--environment", "pr-42", "--dry-run"]
    old, old_calls = _run(TWIN, tmp_path, args, with_gh=True, FAKE_GH_IDS="101")
    bad, bad_calls = _run(mutant, tmp_path, args, with_gh=True, FAKE_GH_IDS="101")
    assert old_calls == [LIST_CALL], "the TWIN deleted during a dry run; the plant is untested"
    assert any("DELETE" in call for call in bad_calls), (
        "the mutant did not delete; plant did not fire"
    )
    assert bad.returncode == old.returncode, (
        "the plant is invisible in the exit code, which is why the call log is compared"
    )

    good, good_calls = _run(PORT, tmp_path, args, with_gh=True, FAKE_GH_IDS="101")
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stderr == old.stderr
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
