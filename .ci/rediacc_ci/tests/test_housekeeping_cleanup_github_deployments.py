"""`rediacc_ci.housekeeping.cleanup_github_deployments`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/housekeeping/cleanup-github-deployments.sh` and the port over the same fixture and compared exit code, stdout, stderr and the `gh` call log. The K=5 ledger `.ci/shadow/w7p6-cleanup-github-deployments.observations.jsonl` recorded that comparison over five distinct trees, in a disposable scratch repo outside this checkout.
The twin has now been deleted and every case that executed it compares against `goldens/cleanup-github-deployments/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

A RECORDING FAKE `gh`, written as Python, seam is PATH -- ruling 7's shape, as in `test_pr_sync_epic_block.py`. Nothing here reaches the network, and the real `gh` on this machine is never on the PATH handed to the subject. That is not merely tidy: this script's non-dry-run arm DELETES deployment records, and its `--repo` comes from the command line, so a case that leaked the
real binary would delete real records from whatever repository the argument named.

THE CALL LOG IS THE PRIMARY ARTIFACT, not stdout. This script writes NOTHING to stdout (every message is `log_*`, which is stderr), and its whole observable effect is the sequence of `gh` invocations. So every golden carries the recorded call sequence beside the two streams: a port that printed the right messages while making the wrong requests would otherwise pass.

TWO CASES PIN DEFECTS IN THE TWIN RATHER THAN CORRECT BEHAVIOUR, and say so in their own names, so a future fix turns them red instead of sliding past: `test_defect_failed_deletions_do_not_affect_the_exit_code` and `test_defect_the_environment_is_not_url_encoded`. Both are described in the port's module docstring.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.housekeeping import cleanup_github_deployments as port
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "housekeeping" / "cleanup_github_deployments.py"
BASH = shutil.which("bash") or "/bin/bash"

SLUG = "cleanup-github-deployments"

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

# What the subject needs on PATH besides the fake gh. The twin sourced common.sh (`dirname` at line 15, `uname` for the CI_OS/CI_ARCH assignments at source time) and its `parse_args` called `to_upper`, which shells out to `tr` once per flag (common.sh:301-303). Found by driving it: the first attempt omitted `tr` and every argument-parsing case died with "common.sh: line 302:
# tr: command not found", exit 127.
PATH_MINIMUM = ("dirname", "uname", "tr")

CALLS_MARKER = "--- calls ---\n"


def _bin(tmp_path: pathlib.Path, name: str, *, with_gh: bool = True) -> str:
    stub = tmp_path / name
    stub.mkdir(parents=True, exist_ok=True)
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
    subject: pathlib.Path,
    tmp_path: pathlib.Path,
    args: list[str],
    *,
    with_gh: bool = True,
    side: str = "new",
    **gh_env: str,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
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


LIST_CALL = (
    "api\trepos/acme/widget/deployments?environment=pr-42&per_page=100\t--paginate\t--jq\t.[].id"
)

BASE = ["--repo", "acme/widget", "--environment", "pr-42"]

CASE_KW: dict[str, tuple[list[str], dict[str, object]]] = {
    "no-arguments": ([], {}),
    "a-repo-without-an-environment": (["--repo", "acme/widget"], {}),
    "an-environment-without-a-repo": (["--environment", "pr-42"], {}),
    "a-missing-gh": ([], {"with_gh": False}),
    "no-deployments-found": (BASE, {"FAKE_GH_IDS": ""}),
    "a-dry-run-over-three-ids": ([*BASE, "--dry-run"], {"FAKE_GH_IDS": "101,102,103"}),
    "a-dry-run-over-two-ids": ([*BASE, "--dry-run"], {"FAKE_GH_IDS": "101,102"}),
    "the-real-path-over-two-ids": (BASE, {"FAKE_GH_IDS": "101,102"}),
    "the-real-path-over-one-id": (BASE, {"FAKE_GH_IDS": "101"}),
    "one-deletion-fails": (
        BASE,
        {"FAKE_GH_IDS": "101,102,103", "FAKE_GH_DELETE_FAILS": "102"},
    ),
    "every-deletion-fails": (
        BASE,
        {"FAKE_GH_IDS": "101,102", "FAKE_GH_DELETE_FAILS": "101,102"},
    ),
    "an-unencoded-environment": (
        ["--repo", "acme/widget", "--environment", "pr-1&per_page=1"],
        {"FAKE_GH_IDS": ""},
    ),
    "dry-run-false-is-not-a-dry-run": ([*BASE, "--dry-run", "false"], {"FAKE_GH_IDS": "101"}),
    "a-failing-listing": (BASE, {"FAKE_GH_LIST_RC": "7"}),
}

CASES = tuple(CASE_KW)


def render(proc, calls: list[str]) -> str:
    body = frozen.render(proc.returncode, proc.stdout, proc.stderr)
    return body + CALLS_MARKER + "".join("%s\n" % line for line in calls)


def recorded(name: str) -> tuple[int, str, str, list[str]]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    streams, calls_text = rest.split(CALLS_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        [line for line in calls_text.splitlines() if line],
    )


def drive(tmp_path: pathlib.Path, name: str, *, subject: pathlib.Path | None = None):
    args, kw = CASE_KW[name]
    return _run(subject or PORT, tmp_path, args, **kw)  # type: ignore[arg-type]


def compare(tmp_path: pathlib.Path, name: str, *, subject: pathlib.Path | None = None):
    want_exit, want_out, want_err, want_calls = recorded(name)
    proc, calls = drive(tmp_path, name, subject=subject)
    assert proc.returncode == want_exit, (
        f"{name}: the twin exited {want_exit}, the port {proc.returncode}"
    )
    assert proc.stdout == want_out, f"{name}: stdout diverged from the recorded bytes"
    assert proc.stderr == want_err, f"{name}: stderr diverged from the recorded bytes"
    assert calls == want_calls, f"{name}: the gh call sequence diverged:\n{want_calls}\n{calls}"
    return proc, calls


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_no_arguments_prints_the_usage() -> None:
    returncode, stdout, stderr, calls = recorded("no-arguments")
    assert returncode == 1
    assert stdout == ""
    assert stderr == (
        "✗ Usage: cleanup-github-deployments.sh --repo <owner/repo> "
        "--environment <name> [--dry-run]\n"
    )
    assert calls == [], "gh was called before the arguments were validated"


def test_repo_without_environment_prints_the_usage() -> None:
    assert recorded("a-repo-without-an-environment")[0] == 1


def test_environment_without_repo_prints_the_usage() -> None:
    assert recorded("an-environment-without-a-repo")[0] == 1


def test_missing_gh_refuses_before_the_usage_check() -> None:
    """ORDER MATTERS AND IS REPRODUCED: `require_cmd gh` ran BEFORE the argument validation, so a machine without gh reports the missing binary even when the command line is also wrong."""
    returncode, _, stderr, _ = recorded("a-missing-gh")
    assert returncode == 1
    assert stderr == "✗ Required command 'gh' is not available\n"


def test_no_deployments_found() -> None:
    returncode, stdout, stderr, calls = recorded("no-deployments-found")
    assert returncode == 0
    assert stdout == ""
    assert stderr.endswith("✓ No deployments found for pr-42\n")
    assert calls == [LIST_CALL]


def test_dry_run_deletes_nothing() -> None:
    """THE SAFE PATH, and the assertion that matters is the CALL LOG: exactly one listing call and not a single DELETE."""
    returncode, _, stderr, calls = recorded("a-dry-run-over-three-ids")
    assert returncode == 0
    assert "⚠ DRY-RUN mode: no deletions will be performed" in stderr
    assert "⚠ [DRY-RUN] Would delete deployment 101 (pr-42)" in stderr
    assert stderr.endswith("✓ Would delete 3 deployment(s) for pr-42\n")
    assert calls == [LIST_CALL], f"dry-run made mutating calls: {calls}"


def test_real_path_marks_inactive_then_deletes_each_id() -> None:
    returncode, _, stderr, calls = recorded("the-real-path-over-two-ids")
    assert returncode == 0
    assert stderr.endswith("✓ Deleted 2 of 2 deployment(s) for pr-42\n")
    assert calls == [
        LIST_CALL,
        "api\trepos/acme/widget/deployments/101/statuses\t-X\tPOST\t-f\tstate=inactive",
        "api\t-X\tDELETE\trepos/acme/widget/deployments/101",
        "api\trepos/acme/widget/deployments/102/statuses\t-X\tPOST\t-f\tstate=inactive",
        "api\t-X\tDELETE\trepos/acme/widget/deployments/102",
    ]


def test_gh_output_from_the_mutating_calls_is_swallowed(tmp_path: pathlib.Path) -> None:
    """`>/dev/null 2>&1` on BOTH mutation calls. The fake writes to both streams precisely so a port that forgot one is caught here."""
    _, stdout, stderr, _ = recorded("the-real-path-over-one-id")
    assert "must never be seen" not in stdout + stderr
    proc, _ = compare(tmp_path, "the-real-path-over-one-id")
    assert "must never be seen" not in proc.stdout + proc.stderr


def test_a_failed_deletion_warns_and_the_others_still_run() -> None:
    _, _, stderr, calls = recorded("one-deletion-fails")
    assert "⚠ Failed to delete deployment 102 (pr-42)" in stderr
    assert stderr.endswith("✓ Deleted 2 of 3 deployment(s) for pr-42\n")
    assert any("deployments/103" in call for call in calls), "the loop stopped at the failure"


def test_defect_failed_deletions_do_not_affect_the_exit_code() -> None:
    """PINNING A DEFECT, NOT A REQUIREMENT. Every deletion failed and the script still exited 0, so a workflow step shows a green tick while the Deployments view is untouched. Reported to the driver rather than fixed here: changing it changes live release-path behaviour. If the port is ever fixed, THIS TEST GOES RED, which is the point."""
    returncode, _, stderr, _ = recorded("every-deletion-fails")
    assert returncode == 0, "the twin failed on a failed deletion; update this test"
    assert stderr.endswith("✓ Deleted 0 of 2 deployment(s) for pr-42\n")


def test_defect_the_environment_is_not_url_encoded() -> None:
    """PINNING A DEFECT. An environment name carrying `&` was interpolated raw into the query string, so the request asks for something else entirely. Latent today (every caller passes `pr-<n>`), reproduced on both sides."""
    assert recorded("an-unencoded-environment")[3] == [
        (
            "api\trepos/acme/widget/deployments?environment=pr-1&per_page=1&per_page=100"
            "\t--paginate\t--jq\t.[].id"
        )
    ]


def test_dry_run_false_is_not_a_dry_run() -> None:
    """common.sh's parse_args QUIRK 2: `--dry-run false` consumed the next token as the VALUE, so DRY_RUN was the string `false` and the deletions were real. Surprising, live, and identical on both sides."""
    returncode, _, stderr, calls = recorded("dry-run-false-is-not-a-dry-run")
    assert returncode == 0
    assert "DRY-RUN" not in stderr
    assert any("DELETE" in call for call in calls), "the twin treated it as a dry run"


def test_listing_failure_propagates_with_ghs_own_stderr() -> None:
    """The listing was `$(gh ...)` with stderr INHERITED, so gh's diagnostic reaches the caller and `set -e` takes the exit code."""
    returncode, _, stderr, _ = recorded("a-failing-listing")
    assert returncode == 7
    assert "fake listing failure (HTTP 403)" in stderr, "the twin swallowed gh's stderr"


def test_nothing_is_ever_written_to_stdout(tmp_path: pathlib.Path) -> None:
    """Every message is `log_*`, which is stderr. A port that used `print()`
    for progress would look right in a terminal and corrupt a pipe."""
    _, want_out, want_err, _ = recorded("a-dry-run-over-two-ids")
    assert want_out == "", f"the TWIN wrote to stdout: {want_out!r}"
    assert want_err != ""
    proc, _ = compare(tmp_path, "a-dry-run-over-two-ids")
    assert proc.stdout == "", f"the PORT wrote to stdout: {proc.stdout!r}"


def test_pure_url_builders() -> None:
    assert port.list_path("a/b", "pr-1") == "repos/a/b/deployments?environment=pr-1&per_page=100"
    assert port.statuses_path("a/b", "9") == "repos/a/b/deployments/9/statuses"
    assert port.delete_path("a/b", "9") == "repos/a/b/deployments/9"


# --------------------------------------------------------------------------- The controls: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_dry_run_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the line that makes `--dry-run` safe. Removing the `continue` turns the dry run into a real one: the messages stay identical, the exit code stays 0, and only the CALL LOG shows that records were deleted -- which is exactly why every golden carries the call log. Driven red against the recording, then the source is confirmed byte-identical and
    green."""
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

    assert recorded("a-dry-run-over-two-ids")[3] == [LIST_CALL], (
        "the TWIN deleted during a dry run; the plant is untested"
    )
    _, bad_calls = drive(tmp_path / "bad", "a-dry-run-over-two-ids", subject=mutant)
    assert any("DELETE" in call for call in bad_calls), "the mutant did not delete"
    with pytest.raises(AssertionError):
        compare(tmp_path / "bad2", "a-dry-run-over-two-ids", subject=mutant)

    compare(tmp_path / "good", "a-dry-run-over-two-ids")
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )


def test_a_planted_removal_of_the_inactive_status_call_is_caught(tmp_path: pathlib.Path) -> None:
    """THE NEW CONTROL ON THE GOLDENS. Delete without marking the deployment inactive first.

    The POST is best-effort (`|| true` in the twin), it prints nothing, and dropping it changes no message and no exit code, so a reader tidying away a call whose result is ignored would see nothing break. GitHub refuses to delete a deployment that is still active, so the recorded call log -- where every id is marked inactive immediately before its DELETE -- is the only witness.
    The mutation is written to a throwaway file; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = (
        "        _gh_silent(\n"
        '            ["api", statuses_path(repo, deployment_id), "-X", "POST", "-f", '
        '"state=inactive"]\n'
        "        )\n"
    )
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(original.replace(anchor, ""), encoding="utf-8")

    with pytest.raises(AssertionError):
        compare(tmp_path / "bad", "the-real-path-over-two-ids", subject=mutant)
    compare(tmp_path / "good", "the-real-path-over-two-ids")
    assert PORT.read_text(encoding="utf-8") == original
