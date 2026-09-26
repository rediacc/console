"""`rediacc_ci.housekeeping.cleanup_pr_environments`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/housekeeping/cleanup-pr-environments.sh` and the port over the same fixture and compared exit code, stdout, stderr and the `gh` call log. The K=5 ledger `.ci/shadow/w7p6-cleanup-pr-environments.observations.jsonl` recorded that comparison over five distinct trees, in a disposable scratch repo outside this checkout. The
twin has now been deleted and every case that executed it compares against `goldens/cleanup-pr-environments/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

A RECORDING FAKE `gh` ON PATH, the seam its sibling `test_housekeeping_cleanup_github_deployments.py` established. Nothing here reaches the network, and the real `gh` is never on the PATH handed to the subject. That is not tidiness: this script DELETES GitHub environment objects, which GitHub cannot restore, and its `--repo` comes straight from the command line, so a case
that leaked the real binary would delete real environments from whatever repository the argument named.

THE CALL LOG IS THE PRIMARY ARTIFACT. The script writes nothing to stdout, and its whole observable effect is the sequence of `gh` invocations, so every golden carries the recorded sequence beside both streams and the exit code. A port that printed the right messages while calling `gh api -X DELETE` on `edge` would pass a stdout-only comparison.

ONE CASE PINS A DEFECT rather than a requirement, and says so in its name: `test_defect_no_pr_environments_exits_1_in_silence`. The twin's "No pr-N environments found" branch was unreachable because `grep`'s exit 1 reached the `set -e` that sourcing common.sh switched back on. It is described in the port's module docstring; if the port is ever fixed, that test goes red,
which is the point.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.housekeeping import cleanup_pr_environments as port
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "housekeeping" / "cleanup_pr_environments.py"
BASH = shutil.which("bash") or "/bin/bash"

SLUG = "cleanup-pr-environments"

# THE DELETE BRANCH KEYS OFF argv[-1], NOT THE FIRST NON-FLAG TOKEN. Written the obvious way first, the fake read `DELETE` itself as the path (it does not start
# with `-`), so FAKE_GH_DELETE_FAILS never matched and a "failed deletion" case
# silently exercised the success path. The control did not fire, and the control was the thing that was wrong.
FAKE_GH = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write("\\t".join(argv) + "\\n")

if argv[:1] == ["pr"]:
    state = os.environ.get("FAKE_GH_PR_STATE", "CLOSED")
    if state == "__FAIL__":
        sys.stdout.write(os.environ.get("FAKE_GH_PR_PARTIAL", ""))
        sys.stderr.write("gh: fake pr view failure\\n")
        sys.exit(1)
    sys.stdout.write(state + "\\n")
    sys.exit(0)

if "DELETE" in argv:
    name = argv[-1].rsplit("/", 1)[-1]
    sys.stdout.write("fake DELETE stdout that must never be seen\\n")
    sys.stderr.write("fake DELETE stderr that must never be seen\\n")
    sys.exit(1 if name in os.environ.get("FAKE_GH_DELETE_FAILS", "").split(",") else 0)

if "/deployments?" in " ".join(argv):
    n = os.environ.get("FAKE_GH_NDEP", "0")
    if n == "__FAIL__":
        sys.stderr.write("gh: fake deployments failure\\n")
        sys.exit(1)
    sys.stdout.write(n + "\\n")
    sys.exit(0)

# The environment listing.
names = os.environ.get("FAKE_GH_ENVS", "")
if names:
    sys.stdout.write(names.replace(",", "\\n") + "\\n")
sys.exit(int(os.environ.get("FAKE_GH_LIST_RC", "0")))
"""

# What the subject needs on PATH besides the fake gh: `dirname`/`uname` from sourcing common.sh, `tr` from its parse_args, and `grep`/`sort`, which WERE the twin's environment filter. Found by driving it, the sibling's way.
PATH_MINIMUM = ("dirname", "uname", "tr", "grep", "sort")

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
    call_log = tmp_path / f"{side}-gh-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, f"{side}-bin", with_gh=with_gh),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(call_log),
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
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls


LIST_CALL = "api\trepos/acme/widget/environments\t--paginate\t--jq\t.environments[]?.name"

REPO = ["--repo", "acme/widget"]


def _pr_view(num: str) -> str:
    return f"pr\tview\t{num}\t--repo\tacme/widget\t--json\tstate\t--jq\t.state"


def _dep_count(env: str) -> str:
    return f"api\trepos/acme/widget/deployments?environment={env}&per_page=100\t--jq\tlength"


def _delete(env: str) -> str:
    return f"api\t-X\tDELETE\trepos/acme/widget/environments/{env}"


CASE_KW: dict[str, tuple[list[str], dict[str, object]]] = {
    "no-arguments": ([], {}),
    "a-missing-gh": ([], {"with_gh": False}),
    "no-pr-environments": (REPO, {"FAKE_GH_ENVS": "edge,stable,production-eu"}),
    "an-empty-listing": (REPO, {"FAKE_GH_ENVS": ""}),
    "a-failing-listing-that-still-matched": (
        REPO,
        {"FAKE_GH_ENVS": "pr-5", "FAKE_GH_LIST_RC": "7"},
    ),
    "the-filter-and-the-sort-order": (
        REPO,
        {"FAKE_GH_ENVS": "pr-10,edge,pr-2,production-eu,pr-010"},
    ),
    "a-dry-run-over-pr-1-and-pr-3": ([*REPO, "--dry-run"], {"FAKE_GH_ENVS": "pr-1,pr-3"}),
    "a-dry-run-over-pr-1-and-pr-2": ([*REPO, "--dry-run"], {"FAKE_GH_ENVS": "pr-1,pr-2"}),
    "an-open-pr": (REPO, {"FAKE_GH_ENVS": "pr-5", "FAKE_GH_PR_STATE": "OPEN"}),
    "an-environment-holding-records": (REPO, {"FAKE_GH_ENVS": "pr-5", "FAKE_GH_NDEP": "3"}),
    "an-unknown-deployment-count": (REPO, {"FAKE_GH_ENVS": "pr-5", "FAKE_GH_NDEP": "__FAIL__"}),
    "a-failed-pr-view": (REPO, {"FAKE_GH_ENVS": "pr-5", "FAKE_GH_PR_STATE": "__FAIL__"}),
    "a-partial-pr-view": (
        REPO,
        {
            "FAKE_GH_ENVS": "pr-5",
            "FAKE_GH_PR_STATE": "__FAIL__",
            "FAKE_GH_PR_PARTIAL": "HALF\n",
        },
    ),
    "a-failed-deletion": (REPO, {"FAKE_GH_ENVS": "pr-5,pr-6", "FAKE_GH_DELETE_FAILS": "pr-5"}),
    "one-environment-deleted": (REPO, {"FAKE_GH_ENVS": "pr-5"}),
    "dry-run-false-is-not-a-dry-run": ([*REPO, "--dry-run", "false"], {"FAKE_GH_ENVS": "pr-5"}),
    "a-pr-environment-beside-a-production-one": (REPO, {"FAKE_GH_ENVS": "pr-2,production-eu"}),
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
    assert stderr == ("✗ Usage: cleanup-pr-environments.sh --repo <owner/repo> [--dry-run]\n")
    assert calls == [], "gh was called before --repo was validated"


def test_missing_gh_refuses_before_the_usage_check() -> None:
    """ORDER MATTERS AND IS REPRODUCED: `require_cmd gh` ran before the `--repo` check, so a machine without gh reports the missing binary even when the command line is also wrong."""
    returncode, _, stderr, _ = recorded("a-missing-gh")
    assert returncode == 1
    assert stderr == "✗ Required command 'gh' is not available\n"


def test_defect_no_pr_environments_exits_1_in_silence() -> None:
    """PINNING A DEFECT, NOT A REQUIREMENT. The listing held `edge`, `stable`
    and `production-eu`; nothing matched `^pr-[0-9]+$`; `grep` exited 1;
    `pipefail` handed that to the assignment; and the `-e` that sourcing common.sh switched back on killed the script before its own "No pr-N environments found" branch could run. The operator sees one step line and a bare exit 1 where the correct answer is a green no-op."""
    returncode, stdout, stderr, calls = recorded("no-pr-environments")
    assert returncode == 1, "the twin survived an empty match; update this test"
    assert stdout == ""
    assert stderr == "→ Cleaning up empty pr-N environments in acme/widget\n"
    assert "No pr-N environments found" not in stderr
    assert calls == [LIST_CALL]


def test_an_empty_listing_is_the_same_silent_exit_1() -> None:
    assert recorded("an-empty-listing")[0] == 1


def test_a_failing_listing_that_still_matched_reports_ghs_own_code() -> None:
    """`pipefail` returns the RIGHTMOST non-zero status. gh failed with 7 while still printing a usable name, `grep` and `sort` succeeded, so the pipeline was 7 and `set -e` exited with it. The assignment fails, so nothing is processed at all."""
    returncode, _, _, calls = recorded("a-failing-listing-that-still-matched")
    assert returncode == 7
    assert calls == [LIST_CALL], "the twin processed environments from a failed listing"


def test_only_pr_names_are_touched_and_the_sort_tie_break_matches() -> None:
    """REFUSAL 1 plus the `sort -t- -k2 -n` order. `edge` and `production-eu` are never named in any call, and `pr-2`, `pr-010`, `pr-10` come out in that order: the numeric keys of `010` and `10` tie at 10, and GNU sort's last-resort byte comparison of the whole line puts `pr-010` first."""
    returncode, _, _, calls = recorded("the-filter-and-the-sort-order")
    assert returncode == 0
    assert [c for c in calls if "DELETE" in c] == [
        _delete("pr-2"),
        _delete("pr-010"),
        _delete("pr-10"),
    ]
    assert not any("edge" in c or "production-eu" in c for c in calls)


def test_dry_run_deletes_nothing() -> None:
    returncode, _, stderr, calls = recorded("a-dry-run-over-pr-1-and-pr-3")
    assert returncode == 0
    assert "⚠ DRY-RUN mode: no deletions will be performed" in stderr
    assert "⚠ [DRY-RUN] Would delete environment pr-1 (PR #1 CLOSED, 0 deployments)" in stderr
    assert stderr.endswith("✓ Would delete 2 of 2 pr-N environment(s)\n")
    assert not any("DELETE" in c for c in calls), f"dry-run deleted: {calls}"


def test_an_open_pr_is_skipped_before_the_deployment_count() -> None:
    """REFUSAL 2, and the ORDER is part of it: an OPEN PR was skipped without even asking how many deployments the environment holds."""
    returncode, _, stderr, calls = recorded("an-open-pr")
    assert returncode == 0
    assert "⚠ SKIP pr-5: PR #5 is still OPEN" in stderr
    assert stderr.endswith("✓ Deleted 0 of 1 pr-N environment(s); 1 skipped\n")
    assert calls == [LIST_CALL, _pr_view("5")]


def test_an_environment_holding_records_is_skipped() -> None:
    """REFUSAL 3: the records are `cleanup_github_deployments`'s job."""
    returncode, _, stderr, calls = recorded("an-environment-holding-records")
    assert returncode == 0
    assert (
        "⚠ SKIP pr-5: still holds 3 deployment record(s) -- run "
        "cleanup-github-deployments.sh first" in stderr
    )
    assert calls == [LIST_CALL, _pr_view("5"), _dep_count("pr-5")]


def test_an_unknown_deployment_count_is_also_a_skip() -> None:
    """`|| echo unknown` on a failed count, and `unknown != 0`, so the safe
    branch was taken. "Could not tell" is not "zero" here, which is right."""
    _, _, stderr, calls = recorded("an-unknown-deployment-count")
    assert "still holds unknown deployment record(s)" in stderr
    assert not any("DELETE" in c for c in calls)


def test_a_failed_pr_view_becomes_unknown_and_still_deletes() -> None:
    """`|| echo UNKNOWN`, and UNKNOWN is not OPEN, so the environment IS deleted and the state is carried into the message verbatim."""
    returncode, _, stderr, calls = recorded("a-failed-pr-view")
    assert returncode == 0
    assert "✓ Deleted pr-5 (PR #5 UNKNOWN)" in stderr
    assert _delete("pr-5") in calls


def test_a_partial_pr_view_concatenates_before_unknown() -> None:
    """`$(cmd || echo UNKNOWN)` captured BOTH the failed command's stdout and the fallback, then stripped trailing newlines. A port that returned only the fallback would print `PR #5 UNKNOWN` where the twin printed two lines."""
    assert "HALF\nUNKNOWN" in recorded("a-partial-pr-view")[2]


def test_a_failed_deletion_warns_and_counts_as_skipped() -> None:
    returncode, _, stderr, calls = recorded("a-failed-deletion")
    assert returncode == 0, "a failed deletion still exits 0, as in the sibling script"
    assert "⚠ Failed to delete pr-5 -- this needs a token with Administration:write" in stderr
    assert stderr.endswith("✓ Deleted 1 of 2 pr-N environment(s); 1 skipped\n")
    assert _delete("pr-6") in calls, "the loop stopped at the failure"


def test_gh_output_from_the_delete_is_swallowed(tmp_path: pathlib.Path) -> None:
    """`>/dev/null 2>&1`. The fake writes to both streams precisely so a port that forgot one is caught here."""
    _, want_out, want_err, _ = recorded("one-environment-deleted")
    assert "must never be seen" not in want_out + want_err
    proc, _ = compare(tmp_path, "one-environment-deleted")
    assert "must never be seen" not in proc.stdout + proc.stderr


def test_dry_run_false_is_not_a_dry_run() -> None:
    """parse_args QUIRK 2, live on both sides: `--dry-run false` stored the string `false`, so the deletions were real."""
    _, _, stderr, calls = recorded("dry-run-false-is-not-a-dry-run")
    assert "DRY-RUN" not in stderr
    assert any("DELETE" in c for c in calls), "the twin treated it as a dry run"


def test_nothing_is_ever_written_to_stdout(tmp_path: pathlib.Path) -> None:
    _, want_out, want_err, _ = recorded("a-dry-run-over-pr-1-and-pr-2")
    assert want_out == "", f"the TWIN wrote to stdout: {want_out!r}"
    assert want_err != ""
    proc, _ = compare(tmp_path, "a-dry-run-over-pr-1-and-pr-2")
    assert proc.stdout == "", f"the PORT wrote to stdout: {proc.stdout!r}"


def test_pure_helpers() -> None:
    assert port.environments_path("a/b") == "repos/a/b/environments"
    assert (
        port.deployments_path("a/b", "pr-1")
        == "repos/a/b/deployments?environment=pr-1&per_page=100"
    )
    assert port.environment_path("a/b", "pr-1") == "repos/a/b/environments/pr-1"
    assert port.select_environments(["pr-10", "edge", "pr-2", "pr-010", "pr-x", "xpr-1"]) == [
        "pr-2",
        "pr-010",
        "pr-10",
    ]
    # pipefail: grep's 1 wins when nothing matched, gh's code when something did.
    assert port.pipeline_status(0, 0) == 1
    assert port.pipeline_status(7, 0) == 1
    assert port.pipeline_status(7, 2) == 7
    assert port.pipeline_status(0, 2) == 0


# --------------------------------------------------------------------------- The controls: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_filter_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on refusal 1 -- the filter that keeps `edge` and `production-eu` out of the DELETE loop. The mutant drops the regex test, so the MESSAGES still look plausible and only the CALL LOG shows that `production-eu` was deleted, which is why every golden carries it. Driven red against the recording, then the source is confirmed byte-identical and green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        "    return sorted([n for n in names if PR_ENV_RE.match(n)], key=sort_key)",
        "    return sorted([n for n in names], key=lambda n: (0, n))",
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    name = "a-pr-environment-beside-a-production-one"
    assert not any("production-eu" in c for c in recorded(name)[3]), (
        "the TWIN touched a non-pr environment; the plant is untested"
    )
    _, bad_calls = drive(tmp_path / "bad", name, subject=mutant)
    assert any("production-eu" in c for c in bad_calls), "the mutant did not fire"
    with pytest.raises(AssertionError):
        compare(tmp_path / "bad2", name, subject=mutant)

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )


def test_a_planted_numeric_sort_without_the_tie_break_is_caught(tmp_path: pathlib.Path) -> None:
    """THE NEW CONTROL ON THE GOLDENS. Sort on the number alone.

    `sort -t- -k2 -n` compares field 2 numerically and breaks a tie by comparing the WHOLE line byte-wise, which is why `pr-010` was deleted before `pr-10`. Dropping the tie-break leaves a sort that is correct on every input without a zero-padded duplicate, and Python's stable sort then emits them in listing order instead. Nothing in the tallies moves; only the recorded DELETE
    sequence does. The mutation is written to a throwaway file; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = '    return (int(name.split("-", 1)[1]), name)\n'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(
        original.replace(anchor, '    return (int(name.split("-", 1)[1]), "")\n'),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError):
        compare(tmp_path / "bad", "the-filter-and-the-sort-order", subject=mutant)
    compare(tmp_path / "good", "the-filter-and-the-sort-order")
    assert PORT.read_text(encoding="utf-8") == original
