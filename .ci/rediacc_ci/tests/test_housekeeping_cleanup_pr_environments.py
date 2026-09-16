"""Differential: `rediacc_ci.housekeeping.cleanup_pr_environments` against its
twin `.ci/scripts/housekeeping/cleanup-pr-environments.sh`.

A RECORDING FAKE `gh` ON PATH, the seam its already-ported sibling
`test_housekeeping_cleanup_github_deployments.py` established. Nothing here
reaches the network, and the real `gh` is never on the PATH handed to either
side. That is not tidiness: this script DELETES GitHub environment objects,
which GitHub cannot restore, and its `--repo` comes straight from the command
line, so a case that leaked the real binary would delete real environments from
whatever repository the argument named.

THE CALL LOG IS THE PRIMARY ARTIFACT. The script writes nothing to stdout, and
its whole observable effect is the sequence of `gh` invocations, so every case
compares the recorded sequences as well as both streams and the exit code. A
port that printed the right messages while calling `gh api -X DELETE` on
`edge` would pass a stdout-only comparison.

ONE CASE PINS A DEFECT rather than a requirement, and says so in its name:
`test_defect_no_pr_environments_exits_1_in_silence`. The twin's "No pr-N
environments found" branch is unreachable because `grep`'s exit 1 reaches the
`set -e` that sourcing common.sh switched back on. It is described in the
port's module docstring; if the twin is ever fixed, that test goes red, which
is the point.

K=5 LEDGER: `.ci/shadow/w7p6-cleanup-pr-environments.observations.jsonl` --
five distinct trees, `--assert --k 5` prints "equivalence holds over 5 distinct
trees". Recorded in a disposable scratch repo outside this checkout (`--record`
refuses a dirty tree) with the same fake `gh` on PATH, one scenario per tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.housekeeping import cleanup_pr_environments as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "housekeeping" / "cleanup-pr-environments.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "housekeeping" / "cleanup_pr_environments.py"
BASH = shutil.which("bash") or "/bin/bash"

# THE DELETE BRANCH KEYS OFF argv[-1], NOT THE FIRST NON-FLAG TOKEN. Written the
# obvious way first, the fake read `DELETE` itself as the path (it does not start
# with `-`), so FAKE_GH_DELETE_FAILS never matched and a "failed deletion" case
# silently exercised the success path. The control did not fire, and the control
# was the thing that was wrong.
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

# What both subjects need on PATH besides the fake gh: `dirname`/`uname` from
# sourcing common.sh, `tr` from its parse_args, and `grep`/`sort`, which ARE the
# twin's environment filter. Found by driving it, the sibling's way.
PATH_MINIMUM = ("dirname", "uname", "tr", "grep", "sort")


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


LIST_CALL = "api\trepos/acme/widget/environments\t--paginate\t--jq\t.environments[]?.name"


def _pr_view(num: str) -> str:
    return f"pr\tview\t{num}\t--repo\tacme/widget\t--json\tstate\t--jq\t.state"


def _dep_count(env: str) -> str:
    return f"api\trepos/acme/widget/deployments?environment={env}&per_page=100\t--jq\tlength"


def _delete(env: str) -> str:
    return f"api\t-X\tDELETE\trepos/acme/widget/environments/{env}"


def test_no_arguments_prints_the_usage(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    assert old.returncode == 1
    assert old.stdout == ""
    assert old.stderr == ("✗ Usage: cleanup-pr-environments.sh --repo <owner/repo> [--dry-run]\n")
    assert old_calls == [], "gh was called before --repo was validated"
    _assert_agree(old, new, "no-args", old_calls, new_calls)


def test_missing_gh_refuses_before_the_usage_check(tmp_path: pathlib.Path) -> None:
    """ORDER MATTERS AND IS REPRODUCED: `require_cmd gh` runs before the `--repo`
    check, so a machine without gh reports the missing binary even when the
    command line is also wrong."""
    old, new, old_calls, new_calls = run_both(tmp_path, [], with_gh=False)
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'gh' is not available\n"
    _assert_agree(old, new, "missing-gh", old_calls, new_calls)


def test_defect_no_pr_environments_exits_1_in_silence(tmp_path: pathlib.Path) -> None:
    """PINNING A DEFECT, NOT A REQUIREMENT. The listing holds `edge`, `stable`
    and `production-eu`; nothing matches `^pr-[0-9]+$`; `grep` exits 1;
    `pipefail` hands that to the assignment; and the `-e` that sourcing
    common.sh switched back on kills the script before its own "No pr-N
    environments found" branch can run. The operator sees one step line and a
    bare exit 1 where the correct answer is a green no-op."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--repo", "acme/widget"],
        FAKE_GH_ENVS="edge,stable,production-eu",
    )
    assert old.returncode == 1, "the twin now survives an empty match; update this test"
    assert old.stdout == ""
    assert old.stderr == "→ Cleaning up empty pr-N environments in acme/widget\n"
    assert "No pr-N environments found" not in old.stderr
    assert old_calls == [LIST_CALL]
    _assert_agree(old, new, "no-pr-environments", old_calls, new_calls)


def test_an_empty_listing_is_the_same_silent_exit_1(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--repo", "acme/widget"], FAKE_GH_ENVS="")
    assert old.returncode == 1
    _assert_agree(old, new, "empty-listing", old_calls, new_calls)


def test_a_failing_listing_that_still_matched_reports_ghs_own_code(
    tmp_path: pathlib.Path,
) -> None:
    """`pipefail` returns the RIGHTMOST non-zero status. gh fails with 7 while
    still printing a usable name, `grep` and `sort` succeed, so the pipeline is
    7 and `set -e` exits with it -- after the environments it did see have been
    processed? No: the assignment fails, so nothing is processed at all."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--repo", "acme/widget"], FAKE_GH_ENVS="pr-5", FAKE_GH_LIST_RC="7"
    )
    assert old.returncode == 7
    assert old_calls == [LIST_CALL], "the twin processed environments from a failed listing"
    _assert_agree(old, new, "listing-rc-7", old_calls, new_calls)


def test_only_pr_names_are_touched_and_the_sort_tie_break_matches(
    tmp_path: pathlib.Path,
) -> None:
    """REFUSAL 1 plus the `sort -t- -k2 -n` order. `edge` and `production-eu`
    are never named in any call, and `pr-2`, `pr-010`, `pr-10` come out in that
    order: the numeric keys of `010` and `10` tie at 10, and GNU sort's
    last-resort byte comparison of the whole line puts `pr-010` first."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--repo", "acme/widget"],
        FAKE_GH_ENVS="pr-10,edge,pr-2,production-eu,pr-010",
    )
    assert old.returncode == 0
    assert [c for c in old_calls if "DELETE" in c] == [
        _delete("pr-2"),
        _delete("pr-010"),
        _delete("pr-10"),
    ]
    assert not any("edge" in c or "production-eu" in c for c in old_calls)
    _assert_agree(old, new, "filter-and-sort", old_calls, new_calls)


def test_dry_run_deletes_nothing(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--repo", "acme/widget", "--dry-run"], FAKE_GH_ENVS="pr-1,pr-3"
    )
    assert old.returncode == 0
    assert "⚠ DRY-RUN mode: no deletions will be performed" in old.stderr
    assert "⚠ [DRY-RUN] Would delete environment pr-1 (PR #1 CLOSED, 0 deployments)" in old.stderr
    assert old.stderr.endswith("✓ Would delete 2 of 2 pr-N environment(s)\n")
    assert not any("DELETE" in c for c in old_calls), f"dry-run deleted: {old_calls}"
    _assert_agree(old, new, "dry-run", old_calls, new_calls)


def test_an_open_pr_is_skipped_before_the_deployment_count(tmp_path: pathlib.Path) -> None:
    """REFUSAL 2, and the ORDER is part of it: an OPEN PR is skipped without
    even asking how many deployments the environment holds."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--repo", "acme/widget"], FAKE_GH_ENVS="pr-5", FAKE_GH_PR_STATE="OPEN"
    )
    assert old.returncode == 0
    assert "⚠ SKIP pr-5: PR #5 is still OPEN" in old.stderr
    assert old.stderr.endswith("✓ Deleted 0 of 1 pr-N environment(s); 1 skipped\n")
    assert old_calls == [LIST_CALL, _pr_view("5")]
    _assert_agree(old, new, "open-pr", old_calls, new_calls)


def test_an_environment_holding_records_is_skipped(tmp_path: pathlib.Path) -> None:
    """REFUSAL 3: the records are cleanup-github-deployments.sh's job."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--repo", "acme/widget"], FAKE_GH_ENVS="pr-5", FAKE_GH_NDEP="3"
    )
    assert old.returncode == 0
    assert (
        "⚠ SKIP pr-5: still holds 3 deployment record(s) -- run "
        "cleanup-github-deployments.sh first" in old.stderr
    )
    assert old_calls == [LIST_CALL, _pr_view("5"), _dep_count("pr-5")]
    _assert_agree(old, new, "holds-records", old_calls, new_calls)


def test_an_unknown_deployment_count_is_also_a_skip(tmp_path: pathlib.Path) -> None:
    """`|| echo unknown` on a failed count, and `unknown != 0`, so the safe
    branch is taken. "Could not tell" is not "zero" here, which is right."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--repo", "acme/widget"], FAKE_GH_ENVS="pr-5", FAKE_GH_NDEP="__FAIL__"
    )
    assert "still holds unknown deployment record(s)" in old.stderr
    assert not any("DELETE" in c for c in old_calls)
    _assert_agree(old, new, "unknown-count", old_calls, new_calls)


def test_a_failed_pr_view_becomes_unknown_and_still_deletes(tmp_path: pathlib.Path) -> None:
    """`|| echo UNKNOWN`, and UNKNOWN is not OPEN, so the environment IS
    deleted and the state is carried into the message verbatim."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--repo", "acme/widget"], FAKE_GH_ENVS="pr-5", FAKE_GH_PR_STATE="__FAIL__"
    )
    assert old.returncode == 0
    assert "✓ Deleted pr-5 (PR #5 UNKNOWN)" in old.stderr
    assert _delete("pr-5") in old_calls
    _assert_agree(old, new, "pr-view-fails", old_calls, new_calls)


def test_a_partial_pr_view_concatenates_before_unknown(tmp_path: pathlib.Path) -> None:
    """`$(cmd || echo UNKNOWN)` captures BOTH the failed command's stdout and
    the fallback, then strips trailing newlines. A port that returned only the
    fallback would print `PR #5 UNKNOWN` where the twin prints two lines."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--repo", "acme/widget"],
        FAKE_GH_ENVS="pr-5",
        FAKE_GH_PR_STATE="__FAIL__",
        FAKE_GH_PR_PARTIAL="HALF\n",
    )
    assert "HALF\nUNKNOWN" in old.stderr
    _assert_agree(old, new, "partial-pr-view", old_calls, new_calls)


def test_a_failed_deletion_warns_and_counts_as_skipped(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--repo", "acme/widget"],
        FAKE_GH_ENVS="pr-5,pr-6",
        FAKE_GH_DELETE_FAILS="pr-5",
    )
    assert old.returncode == 0, "a failed deletion still exits 0, as in the sibling script"
    assert "⚠ Failed to delete pr-5 -- this needs a token with Administration:write" in old.stderr
    assert old.stderr.endswith("✓ Deleted 1 of 2 pr-N environment(s); 1 skipped\n")
    assert _delete("pr-6") in old_calls, "the loop stopped at the failure"
    _assert_agree(old, new, "delete-fails", old_calls, new_calls)


def test_gh_output_from_the_delete_is_swallowed(tmp_path: pathlib.Path) -> None:
    """`>/dev/null 2>&1`. The fake writes to both streams precisely so a port
    that forgot one would be caught here."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--repo", "acme/widget"], FAKE_GH_ENVS="pr-5"
    )
    assert "must never be seen" not in old.stdout + old.stderr
    assert "must never be seen" not in new.stdout + new.stderr
    _assert_agree(old, new, "swallowed", old_calls, new_calls)


def test_dry_run_false_is_not_a_dry_run(tmp_path: pathlib.Path) -> None:
    """parse_args QUIRK 2, live on both sides: `--dry-run false` stores the
    string `false`, so the deletions are real."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--repo", "acme/widget", "--dry-run", "false"], FAKE_GH_ENVS="pr-5"
    )
    assert "DRY-RUN" not in old.stderr
    assert any("DELETE" in c for c in old_calls), "the twin treated it as a dry run"
    _assert_agree(old, new, "dry-run-false", old_calls, new_calls)


def test_nothing_is_ever_written_to_stdout(tmp_path: pathlib.Path) -> None:
    old, new, _old_calls, _new_calls = run_both(
        tmp_path, ["--repo", "acme/widget", "--dry-run"], FAKE_GH_ENVS="pr-1,pr-2"
    )
    assert old.stdout == "", f"the TWIN wrote to stdout: {old.stdout!r}"
    assert new.stdout == "", f"the PORT wrote to stdout: {new.stdout!r}"
    assert old.stderr != ""


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


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on refusal 1 -- the filter that keeps `edge` and
    `production-eu` out of the DELETE loop. The mutant drops the regex test, so
    the MESSAGES still look plausible and only the CALL LOG shows that
    `production-eu` was deleted, which is why every case here compares it.
    Driven red, then the source is confirmed byte-identical and green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        "    return sorted([n for n in names if PR_ENV_RE.match(n)], key=sort_key)",
        "    return sorted([n for n in names], key=lambda n: (0, n))",
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    args = ["--repo", "acme/widget"]
    envs = "pr-2,production-eu"
    old, old_calls = _run(TWIN, tmp_path, args, with_gh=True, FAKE_GH_ENVS=envs)
    _bad, bad_calls = _run(mutant, tmp_path, args, with_gh=True, FAKE_GH_ENVS=envs)
    assert not any("production-eu" in c for c in old_calls), (
        "the TWIN touched a non-pr environment; the plant is untested"
    )
    assert any("production-eu" in c for c in bad_calls), "the mutant did not fire"

    good, good_calls = _run(PORT, tmp_path, args, with_gh=True, FAKE_GH_ENVS=envs)
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stderr == old.stderr
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
