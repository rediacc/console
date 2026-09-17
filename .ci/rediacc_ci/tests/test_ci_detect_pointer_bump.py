"""Differential: `rediacc_ci.ci.detect_pointer_bump` against its twin
`.ci/scripts/ci/detect-pointer-bump.sh`.

A REAL GIT REPOSITORY, BUILT WITH PLUMBING, AND A RECORDING FAKE FOR `gh`.

`git` IS NOT STUBBED, and that is the central choice in this file. Every fact this script rules on is `git`'s answer to a question about commit topology and tree content, so a fake `git` would be a fake of the SUBJECT rather than of a dependency: the differential would then prove the two implementations agree about a script's own fixture. Real gitlinks are made without any
submodule at all, with `git update-index --add --cacheinfo 160000,<sha>,<path>`, so `diff-tree -r --raw` produces genuine `:160000 160000` lines and the walk sees real parents, real trees and a real merge commit.

`gh` IS THE ONLY THING FAKED, because it is the only thing that carries a credential and leaves the machine. It records its argv and answers three endpoints: the baseline's check-runs, a submodule commit's tree sha, and the `NEW...main` comparison.

COMMITS ARE MADE WITH `commit-tree`, NOT `git commit`. Two reasons: the working tree never needs a `private/x` directory for a gitlink to exist in the index, and the plumbing form takes explicit dates so a fixture's shas are stable across runs of this file.

THE PROOF THAT THE FIXTURE IS SHAPED LIKE A REAL PULL REQUEST is the merge commit. `actions/checkout` hands a `pull_request` job the synthetic `refs/pull/N/merge` commit, so HEAD is a two-parent merge of the branch tip and the target branch, and the branch tip is only reachable through the event payload. Both of this script's live defects are consequences of that shape, and neither
is visible in a fixture where HEAD is the tip.
"""

from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.ci import detect_pointer_bump as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "ci" / "detect-pointer-bump.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "ci" / "detect_pointer_bump.py"
BASH = shutil.which("bash") or "/bin/bash"

# Real binaries. `git` is the subject, `jq` reads the event payload, `sed` turns a submodule URL into a slug. `grep` and `awk` are the twin's, not the port's: the port reimplements both (see its docstring) and the twin shells out to them, so they have to be here
# for the comparison to be between two working programs.
PATH_MINIMUM = (
    "git",
    "jq",
    "sed",
    "grep",
    "awk",
    "cat",
    "env",
    "uname",
    "tr",
    "dirname",
    "basename",
)

SUBMODULE_PATH = "private/x"
SUBMODULE_URL = "git@github.com:acme/x.git"
SUBMODULE_SLUG = "acme/x"
OLD_POINTER = "1111111111111111111111111111111111111111"
NEW_POINTER = "2222222222222222222222222222222222222222"

# A MODEL of the three `gh api` calls this script makes.
#
# THE `call: ` PREFIX IS LOAD-BEARING FOR THE LEDGER, not decoration. `shadow-gate.ts` classifies any line starting with `→ ` or `✓ ` as CHATTER before a `--finding-re` is consulted, and this script reports ONLY through `log_info`, which is `✓ `. Without a distinctly prefixed line from the fake, every ledger row would read VACUOUS_BOTH_EMPTY however the regex was written.
FAKE_GH = r'''#!/usr/bin/python3
"""Recording fake for `gh api`. See the test module docstring."""
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("call: gh %s\n" % " ".join(argv))
    # THE TOKEN IS PART OF THE OBSERVATION. The twin sets GH_TOKEN as a command
    # prefix, unconditionally, so a port that dropped the assignment (or passed
    # the wrong variable) would still make the same call with a different
    # credential. `<unset>` and an empty value are recorded differently.
    token = os.environ.get("GH_TOKEN")
    fh.write("call: gh-token %s\n" % ("<unset>" if token is None else "[%s]" % token))

path = argv[1] if argv[:1] == ["api"] else ""
for i, a in enumerate(argv):
    if a == "api":
        path = argv[i + 1] if i + 1 < len(argv) else ""
        break
# `-X GET` puts the path one token later; find the first non-flag after `api`.
tokens = [a for a in argv[1:] if not a.startswith("-")]
prev = None
path = ""
for a in argv[1:]:
    if prev in ("-X", "-f", "--jq"):
        prev = a
        continue
    if a.startswith("-"):
        prev = a
        continue
    path = a
    break

if path.endswith("/check-runs"):
    if os.environ.get("FAKE_CHECKRUNS_FAILS") == "1":
        sys.stderr.write("gh: HTTP 403 (fixture)\n")
        sys.exit(1)
    sys.stdout.write("%s\n" % os.environ.get("FAKE_GREEN", "1"))
    sys.exit(0)

if "/compare/" in path:
    if os.environ.get("FAKE_COMPARE_FAILS") == "1":
        sys.stderr.write("gh: HTTP 404 (fixture)\n")
        sys.exit(1)
    sys.stdout.write("%s\n" % os.environ.get("FAKE_COMPARE", "ahead"))
    sys.exit(0)

if "/commits/" in path:
    sha = path.rsplit("/", 1)[1]
    if os.environ.get("FAKE_COMMIT_FAILS_FOR") == sha:
        sys.stderr.write("gh: HTTP 404 (fixture)\n")
        sys.exit(1)
    if os.environ.get("FAKE_TREES") == "differ":
        sys.stdout.write("tree-for-%s\n" % sha)
    else:
        sys.stdout.write("one-shared-tree\n")
    sys.exit(0)

sys.stderr.write("fake gh: unmodelled path %r\n" % (path,))
sys.exit(127)
'''


def _bin(root: pathlib.Path, *, drop: str = "") -> str:
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        link = stub / real_name
        if real_name == drop:
            if link.is_symlink() or link.exists():
                link.unlink()
            continue
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        if not link.exists():
            link.symlink_to(real)
    gh = stub / "gh"
    if drop == "gh":
        if gh.exists():
            gh.unlink()
    else:
        gh.write_text(FAKE_GH, encoding="utf-8")
        gh.chmod(0o755)
    if drop:
        assert shutil.which(drop, path=str(stub)) is None, f"{drop} leaked into the stub PATH"
    return str(stub)


GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_AUTHOR_DATE": "2020-01-01T00:00:00Z",
    "GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(root: pathlib.Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **GIT_IDENTITY},
    )
    return proc.stdout.strip()


def _commit(root: pathlib.Path, message: str, parents: tuple[str, ...] = ()) -> str:
    tree = _git(root, "write-tree")
    args = ["commit-tree", tree]
    for parent in parents:
        args += ["-p", parent]
    return _git(root, *args, "-m", message)


class Repo:
    """The fixture's shas, named the way the twin's header names them."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.base = ""
        self.tip = ""
        self.main = ""
        self.merge = ""


def fixture(
    tmp_path: pathlib.Path,
    *,
    tip_is_pointer_only: bool = True,
    merge_head: bool = True,
    main_moves: bool = False,
    gitmodules: str | None = SUBMODULE_PATH,
    empty_commit: bool = False,
) -> Repo:
    """A repository shaped like a `pull_request` checkout.

      root -- base -- tip          (the branch; `tip` is the event's head.sha)
                \\        \\
                 main ---- merge   (HEAD, when merge_head is True)

    `tip_is_pointer_only` decides whether `tip` moves only the gitlink or also touches a file. `main_moves` gives the target branch a commit of its own, which is what makes the merge's tree differ from the tip's. `gitmodules` names the path recorded in `.gitmodules`, or None to omit the file entirely.
    """
    root = tmp_path / "repo"
    (root / ".ci" / "scripts" / "ci").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "ci" / TWIN.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / COMMON.name)

    _git(root, "init", "-q", "-b", "main")
    repo = Repo(root)

    if gitmodules is not None:
        (root / ".gitmodules").write_text(
            '[submodule "%s"]\n\tpath = %s\n\turl = %s\n' % (gitmodules, gitmodules, SUBMODULE_URL),
            encoding="utf-8",
        )
        _git(root, "add", "--", ".gitmodules")
    (root / "readme.md").write_text("one\n", encoding="utf-8")
    _git(root, "add", "--", "readme.md")
    _git(root, "update-index", "--add", "--cacheinfo", f"160000,{OLD_POINTER},{SUBMODULE_PATH}")
    root_commit = _commit(root, "root")

    # `base`: an ordinary commit, which is what the walk stops at.
    (root / "readme.md").write_text("two\n", encoding="utf-8")
    _git(root, "add", "--", "readme.md")
    repo.base = _commit(root, "base", (root_commit,))

    if empty_commit:
        # A commit whose tree is IDENTICAL to its parent's: `diff-tree --raw` prints nothing at all for it.
        repo.tip = _commit(root, "empty", (repo.base,))
    else:
        _git(root, "update-index", "--add", "--cacheinfo", f"160000,{NEW_POINTER},{SUBMODULE_PATH}")
        if not tip_is_pointer_only:
            (root / "readme.md").write_text("three\n", encoding="utf-8")
            _git(root, "add", "--", "readme.md")
        repo.tip = _commit(root, "tip", (repo.base,))

    if merge_head:
        # The target branch, then the synthetic merge `actions/checkout` builds.
        _git(root, "read-tree", repo.base)
        if main_moves:
            (root / "other.md").write_text("main moved\n", encoding="utf-8")
            _git(root, "add", "--", "other.md")
        repo.main = _commit(root, "main", (repo.base,))
        # The merge's TREE is the tip's tree plus whatever main added, which is what `actions/checkout`'s synthetic merge holds. Built directly rather than with `read-tree -m`, because a three-way merge needs a clean index this fixture never has and the RESULT is the only thing the script looks at.
        _git(root, "read-tree", repo.tip)
        if main_moves:
            (root / "other.md").write_text("main moved\n", encoding="utf-8")
            _git(root, "add", "--", "other.md")
        repo.merge = _commit(root, "merge", (repo.tip, repo.main))
        head = repo.merge
    else:
        head = repo.tip

    _git(root, "update-ref", "refs/heads/main", head)
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")

    (root / "event.json").write_text(
        json.dumps({"pull_request": {"head": {"sha": repo.tip}}}), encoding="utf-8"
    )
    return repo


def _run(
    repo: Repo,
    side: str,
    *,
    args: tuple[str, ...] = (),
    with_event: bool = True,
    drop: str = "",
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    root = repo.root
    call_log = root / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")

    env = {
        "PATH": _bin(root, drop=drop),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "REDIACC_CI_ROOT": str(root),
        "FAKE_CALL_LOG": str(call_log),
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_REPOSITORY": "acme/console",
        "CHECKS_TOKEN": "checks-tok",
        "GITHUB_PAT": "pat-tok",
        **GIT_IDENTITY,
    }
    if with_event:
        env["GITHUB_EVENT_PATH"] = str(root / "event.json")
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)

    if side == "old":
        argv = [BASH, str(root / ".ci" / "scripts" / "ci" / TWIN.name), *args]
    else:
        argv = [sys.executable, str(PORT_FILE), *args]
    proc = subprocess.run(
        argv,
        cwd=str(root.parent),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_both(tmp_path: pathlib.Path, *, fixture_kw: dict | None = None, **kw):
    repo = fixture(tmp_path, **(fixture_kw or {}))
    old = _run(repo, "old", **kw)
    new = _run(repo, "new", **kw)
    return repo, old, new


# THE ONE DIVERGENCE THIS FILE NORMALISES, and it is a bash DIAGNOSTIC rather than either program's own message: bash prefixes its own errors with `<script path>: line <n>: `, where the line number is a fact about the bash file. The port prints `detect-pointer-bump.sh: ` and then the same words.
#
# THE PATTERN IS DELIBERATELY TIGHT: only a leader ending in `detect-pointer-bump.sh`, optionally followed by ` line <digits>`, and the rest of the line is kept and compared. `test_the_bash_diagnostic_normaliser_keeps_the_message` asserts both directions.
BASH_DIAG = re.compile(r"^\S*detect-pointer-bump\.sh: (?:line \d+: )?(?P<rest>.*)$", re.MULTILINE)


def _mask(text: str) -> str:
    return BASH_DIAG.sub(lambda m: "detect-pointer-bump: %s" % m.group("rest"), text)


def _agree(old, new, label: str) -> None:
    """THE THREE STREAMS SEPARATELY, plus the `gh` call log.

    The only normalisation is `_mask`, which collapses bash's own
    `<file>: line <n>:` prefix; see its comment. Nothing else is masked, and the
    commit shas are the SAME repository's, so a mask there could only hide a real difference.
    """
    old_proc, old_calls = old
    new_proc, new_calls = new
    assert new_proc.returncode == old_proc.returncode, (
        f"{label}: exit diverged: {old_proc.returncode!r} vs {new_proc.returncode!r}\n"
        f"old stdout: {old_proc.stdout!r}\nold stderr: {old_proc.stderr!r}\n"
        f"new stdout: {new_proc.stdout!r}\nnew stderr: {new_proc.stderr!r}"
    )
    assert _mask(new_proc.stdout) == _mask(old_proc.stdout), (
        f"{label}: stdout diverged:\n{old_proc.stdout!r}\n{new_proc.stdout!r}"
    )
    assert _mask(new_proc.stderr) == _mask(old_proc.stderr), (
        f"{label}: stderr diverged:\n{old_proc.stderr!r}\n{new_proc.stderr!r}"
    )
    assert new_calls == old_calls, f"{label}: call log diverged:\n{old_calls}\n---\n{new_calls}"


def _calls(log: str) -> list[str]:
    return [line[len("call: ") :] for line in log.splitlines() if line.startswith("call: ")]


def _reason(proc) -> str:
    """The `pointer_bump_only=... -- <reason>` line, without its marker."""
    for line in proc.stderr.splitlines():
        if line.startswith("✓ pointer_bump_only="):
            return line[len("✓ ") :]
    return ""


# --------------------------------------------------------------------------- The fast path, which has never once fired in production ---------------------------------------------------------------------------


def test_the_fast_path_fires_when_every_step_of_the_proof_holds(tmp_path) -> None:
    """HEAD IS THE TIP HERE, deliberately: this is the only shape in which the
    whole proof can complete, and it is NOT the shape a `pull_request` job has.
    See DEFECT A and DEFECT B for what the real shape does."""
    repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False})
    _agree(old, new, "fast-path")

    proc, calls = old
    assert proc.returncode == 0
    assert proc.stdout == "pointer_bump_only=true\nbaseline_sha=%s\n" % repo.base
    assert _reason(proc) == (
        "pointer_bump_only=true -- baseline %s passed CI Complete; "
        "%s %s->%s (tree-identical, on %s main); "
        % (
            repo.base[:7],
            SUBMODULE_PATH,
            OLD_POINTER[:7],
            NEW_POINTER[:7],
            SUBMODULE_SLUG,
        )
    )
    # PRINT THE SHAPE: check-runs once, then two commit reads and one compare.
    gh_paths = [c for c in _calls(calls) if c.startswith("gh api")]
    assert len(gh_paths) == 4, gh_paths
    assert "/check-runs" in gh_paths[0]
    assert gh_paths[1].endswith("--jq .commit.tree.sha")
    assert "/compare/%s...main" % NEW_POINTER in gh_paths[3]


def test_the_two_tokens_are_the_two_different_variables(tmp_path) -> None:
    """`CHECKS_TOKEN` has checks:read on the console repo and `GITHUB_PAT` has
    contents:read on the submodule repos. Swapping them would leave every call
    in the same place and every one of them unauthorised in production."""
    _repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False})
    _agree(old, new, "tokens")

    _proc, calls = old
    tokens = [c[len("gh-token ") :] for c in _calls(calls) if c.startswith("gh-token ")]
    assert tokens == ["[checks-tok]", "[pat-tok]", "[pat-tok]", "[pat-tok]"], tokens


def test_an_unset_token_is_still_exported_as_the_empty_string(tmp_path) -> None:
    """`GH_TOKEN="${CHECKS_TOKEN:-}" gh api` sets the variable EVEN WHEN the
    source is unset, and `gh` refuses differently for an empty token than for an absent one. A port that skipped the assignment would be making the same call
    with a different credential."""
    _repo, old, new = run_both(
        tmp_path, fixture_kw={"merge_head": False}, drop_env=("CHECKS_TOKEN",)
    )
    _agree(old, new, "unset-token")

    _proc, calls = old
    tokens = [c[len("gh-token ") :] for c in _calls(calls) if c.startswith("gh-token ")]
    assert tokens[0] == "[]", "set, and empty, not absent"


def test_the_output_file_receives_both_pairs_and_stdout_still_does(tmp_path) -> None:
    """`$GITHUB_OUTPUT` is APPENDED to, because other steps' pairs are already
    in it. Both sides also print to stdout unconditionally."""
    repo = fixture(tmp_path, merge_head=False)
    out_old = repo.root / "old-output.txt"
    out_new = repo.root / "new-output.txt"
    out_old.write_text("pre_existing=kept\n", encoding="utf-8")
    out_new.write_text("pre_existing=kept\n", encoding="utf-8")
    old = _run(repo, "old", args=("--output", str(out_old)))
    new = _run(repo, "new", args=("--output", str(out_new)))
    _agree(old, new, "output-file")

    assert out_old.read_text(encoding="utf-8") == out_new.read_text(encoding="utf-8")
    assert out_old.read_text(encoding="utf-8") == (
        "pre_existing=kept\npointer_bump_only=true\nbaseline_sha=%s\n" % repo.base
    )


def test_the_step_summary_gets_three_lines_when_the_fast_path_fires(tmp_path) -> None:
    repo = fixture(tmp_path, merge_head=False)
    sum_old = repo.root / "old-summary.md"
    sum_new = repo.root / "new-summary.md"
    old = _run(repo, "old", GITHUB_STEP_SUMMARY=str(sum_old))
    new = _run(repo, "new", GITHUB_STEP_SUMMARY=str(sum_new))
    _agree(old, new, "step-summary")

    assert sum_old.read_text(encoding="utf-8") == sum_new.read_text(encoding="utf-8")
    lines = sum_old.read_text(encoding="utf-8").splitlines()
    assert lines[0] == port.SUMMARY_HEADING
    assert lines[1].startswith("Content-identical to `%s`" % repo.base)
    assert lines[2].endswith("accepts their skips via POINTER_BUMP_ONLY.")


def test_no_step_summary_variable_means_no_summary_and_no_error(tmp_path) -> None:
    _repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False})
    _agree(old, new, "no-summary")
    proc, _log = old
    assert proc.returncode == 0


# --------------------------------------------------------------------------- Every fail-safe reason, each one its own sentence ---------------------------------------------------------------------------


def test_a_push_event_never_reaches_git_at_all(tmp_path) -> None:
    _repo, old, new = run_both(tmp_path, GITHUB_EVENT_NAME="push")
    _agree(old, new, "not-a-pr")

    proc, calls = old
    assert proc.returncode == 0
    assert _reason(proc) == "pointer_bump_only=false -- not a pull_request event"
    assert proc.stdout == "pointer_bump_only=false\nbaseline_sha=\n"
    assert _calls(calls) == []


def test_a_merge_commit_in_the_walk_stops_it(tmp_path) -> None:
    """The event payload is REMOVED here, so `current` falls back to
    `git rev-parse HEAD`, which on this fixture is the merge commit. That is exactly the pre-D9 behaviour the twin's header describes, and it still
    happens whenever the payload is unreadable."""
    repo, old, new = run_both(tmp_path, with_event=False)
    _agree(old, new, "merge-in-walk")

    proc, _log = old
    assert _reason(proc) == (
        "pointer_bump_only=false -- merge commit %s in the walk" % repo.merge[:7]
    )


def test_an_empty_commit_is_refused_by_name(tmp_path) -> None:
    repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False, "empty_commit": True})
    _agree(old, new, "empty-commit")

    proc, _log = old
    assert _reason(proc) == "pointer_bump_only=false -- empty commit %s" % repo.tip[:7]


def test_a_baseline_with_no_green_ci_complete_is_refused(tmp_path) -> None:
    repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False}, FAKE_GREEN="0")
    _agree(old, new, "no-green")

    proc, _log = old
    assert _reason(proc) == (
        "pointer_bump_only=false -- baseline %s has no successful CI Complete" % repo.base[:7]
    )


def test_a_check_runs_lookup_that_fails_is_refused_and_not_assumed_green(
    tmp_path,
) -> None:
    """AN API CALL THAT COULD NOT RUN IS NOT A PASS. This is the one place this
    script gets that right, and it is worth pinning: `gh` exits 1, its stderr is discarded, and the script refuses rather than treating an unknown as a
    green."""
    repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False}, FAKE_CHECKRUNS_FAILS="1")
    _agree(old, new, "checkruns-fails")

    proc, _log = old
    assert _reason(proc) == (
        "pointer_bump_only=false -- check-runs lookup failed for baseline %s" % repo.base[:7]
    )


def test_an_empty_check_runs_answer_is_zero_and_refuses(tmp_path) -> None:
    """`[[ "${green:-0}" -ge 1 ]]` is ARITHMETIC, so an EMPTY answer takes the
    `:-0` default and refuses. That is the well-behaved half; the other half is
    DEFECT D below."""
    _repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False}, FAKE_GREEN="")
    _agree(old, new, "empty-green")
    proc, _log = old
    assert proc.returncode == 0
    assert "has no successful CI Complete" in _reason(proc)


def test_defect_d_a_non_numeric_check_runs_answer_is_a_hard_exit_1(tmp_path) -> None:
    """A BARE WORD IN A BASH ARITHMETIC CONTEXT IS A VARIABLE REFERENCE, and an
    unset one under `set -u` ends the script: exit 1, nothing on stdout, and no `pointer_bump_only` pair for the caller to read. Every other doubt in this file is exit 0 with a reason.

    Not reachable through today's `gh --jq '... | length'`, which answers with a
    number or fails; one shape change in that jq program away, and the same
    class as DEFECT C."""
    assert port.A_NON_NUMERIC_CHECK_RUNS_ANSWER_IS_A_HARD_EXIT_TOO
    _repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False}, FAKE_GREEN="null")
    _agree(old, new, "null-green")

    proc, _log = old
    assert proc.returncode == 1
    assert proc.stdout == "", "not even a pointer_bump_only pair"
    assert proc.stderr.rstrip().endswith("null: unbound variable")


def test_a_malformed_number_is_false_without_stopping(tmp_path) -> None:
    """`08` and `1a` are BAD NUMBERS rather than variables: bash complains,
    evaluates the test as false, and carries on. The distinction is the whole
    reason DEFECT D is about bare words specifically."""
    _repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False}, FAKE_GREEN="08")
    _agree(old, new, "octal-green")
    proc, _log = old
    assert proc.returncode == 0
    assert "has no successful CI Complete" in _reason(proc)


def test_trees_that_differ_are_refused_with_both_short_shas(tmp_path) -> None:
    _repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False}, FAKE_TREES="differ")
    _agree(old, new, "trees-differ")

    proc, _log = old
    assert _reason(proc) == (
        "pointer_bump_only=false -- %s trees differ (%s vs %s -- submodule main moved?)"
        % (SUBMODULE_PATH, OLD_POINTER[:7], NEW_POINTER[:7])
    )


def test_a_commit_the_pat_cannot_read_is_refused(tmp_path) -> None:
    _repo, old, new = run_both(
        tmp_path, fixture_kw={"merge_head": False}, FAKE_COMMIT_FAILS_FOR=NEW_POINTER
    )
    _agree(old, new, "commit-unreadable")

    proc, _log = old
    assert _reason(proc) == (
        "pointer_bump_only=false -- cannot read %s@%s" % (SUBMODULE_SLUG, NEW_POINTER[:7])
    )


def test_a_new_commit_that_is_not_on_the_submodules_main_is_refused(tmp_path) -> None:
    """`behind` and `diverged` both mean the pointer moved somewhere that is not
    an ancestor of main, which is the case this whole check exists for."""
    for status in ("behind", "diverged"):
        _repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False}, FAKE_COMPARE=status)
        _agree(old, new, f"compare-{status}")
        proc, _log = old
        assert _reason(proc) == (
            "pointer_bump_only=false -- %s new commit not on %s main (status: %s)"
            % (SUBMODULE_PATH, SUBMODULE_SLUG, status)
        )


def test_identical_counts_as_merged_and_ahead_does_too(tmp_path) -> None:
    """THE POSITIVE CONTROL FOR THE ABOVE. Without it, a port that refused
    everything would pass every one of these refusal tests."""
    _repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False}, FAKE_COMPARE="identical")
    _agree(old, new, "compare-identical")
    proc, _log = old
    assert "pointer_bump_only=true" in _reason(proc)


def test_a_compare_call_that_fails_is_refused(tmp_path) -> None:
    _repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False}, FAKE_COMPARE_FAILS="1")
    _agree(old, new, "compare-fails")
    proc, _log = old
    assert _reason(proc) == "pointer_bump_only=false -- compare failed for %s" % SUBMODULE_SLUG


# --------------------------------------------------------------------------- The three named defects ---------------------------------------------------------------------------


def test_defect_a_the_head_guard_cannot_fire_on_a_pull_request(tmp_path) -> None:
    """A PR whose tip is an ORDINARY commit. `current` is the tip (from the
    payload) and `head_sha` is the merge commit, so the `current == head_sha`
    test at :138 is false, the loop breaks with no baseline, and the operator is told `no baseline within 5 commits` about a branch whose very first commit
    was the answer."""
    assert port.THE_HEAD_GUARD_IS_UNREACHABLE_ON_A_PULL_REQUEST
    _repo, old, new = run_both(tmp_path, fixture_kw={"tip_is_pointer_only": False})
    _agree(old, new, "defect-a")

    proc, calls = old
    assert proc.returncode == 0
    assert _reason(proc) == "pointer_bump_only=false -- no baseline within 5 commits"
    assert "HEAD is not a pointer-only commit" not in proc.stderr
    assert _calls(calls) == [], "it never even reaches the check-runs lookup"


def test_defect_a_control_the_guard_does_fire_when_head_really_is_the_tip(
    tmp_path,
) -> None:
    """THE CONTROL. The identical repository WITHOUT the synthetic merge commit
    reports the intended message, which is what makes the case above a defect in
    the SHAPE rather than dead code."""
    _repo, old, new = run_both(
        tmp_path, fixture_kw={"tip_is_pointer_only": False, "merge_head": False}
    )
    _agree(old, new, "defect-a-control")

    proc, _log = old
    assert _reason(proc) == "pointer_bump_only=false -- HEAD is not a pointer-only commit"


def test_defect_b_step_three_diffs_against_the_merge_commit(tmp_path) -> None:
    """A PR whose tip IS pointer-only, on a target branch that has moved. The
    walk succeeds and the baseline passes CI, and then the net diff -- taken against HEAD, the merge -- carries main's file change and the fast path is
    refused for a branch that qualifies."""
    assert port.STEP_THREE_STILL_COMPARES_AGAINST_THE_MERGE_COMMIT
    _repo, old, new = run_both(tmp_path, fixture_kw={"main_moves": True})
    _agree(old, new, "defect-b")

    proc, calls = old
    assert _reason(proc) == ("pointer_bump_only=false -- net diff vs baseline is not gitlink-only")
    # It got PAST the check-runs lookup, which is what makes this step 3's fault rather than the walk's.
    assert [c for c in _calls(calls) if "/check-runs" in c]


def test_defect_b_control_an_unmoved_target_branch_still_fast_paths(tmp_path) -> None:
    """THE CONTROL. Same PR shape, same merge commit, main NOT moved: the
    merge's tree equals the tip's, the net diff is gitlink-only, and the fast path fires. So the refusal above is caused by main moving and by nothing
    else."""
    repo, old, new = run_both(tmp_path, fixture_kw={"main_moves": False})
    _agree(old, new, "defect-b-control")

    proc, _log = old
    assert "pointer_bump_only=true" in _reason(proc)
    assert proc.stdout == "pointer_bump_only=true\nbaseline_sha=%s\n" % repo.base


def test_defect_c_a_gitmodules_with_no_entries_is_a_hard_exit_1(tmp_path) -> None:
    """EVERY OTHER DOUBT IN THIS SCRIPT IS EXIT 0 WITH A REASON. This one is
    exit 1 with nothing: `git config --get-regexp` matches nothing, `pipefail` makes that the assignment's status, and `set -e` ends the run before the guard on the next line is reached. The caller (`initialize.sh`) sees a
    failed step."""
    assert port.AN_EMPTY_GITMODULES_IS_A_HARD_EXIT_NOT_A_FAIL_SAFE
    _repo, old, new = run_both(tmp_path, fixture_kw={"merge_head": False, "gitmodules": None})
    _agree(old, new, "defect-c")

    proc, _log = old
    assert proc.returncode == 1, "not the fail-safe exit 0 every other doubt uses"
    assert "no .gitmodules entry" not in proc.stderr, "the guard never ran"
    assert proc.stdout == "", "not even a pointer_bump_only pair was written"


def test_defect_c_control_a_gitmodules_naming_another_path_does_reach_the_guard(
    tmp_path,
) -> None:
    """THE CONTROL, and the reason DEFECT C is about the EMPTY case specifically.
    With `.gitmodules` naming some OTHER submodule, `git config` succeeds, the
    awk filter finds no match, and the intended fail-safe message appears."""
    _repo, old, new = run_both(
        tmp_path, fixture_kw={"merge_head": False, "gitmodules": "private/other"}
    )
    _agree(old, new, "defect-c-control")

    proc, _log = old
    assert proc.returncode == 0
    assert _reason(proc) == (
        "pointer_bump_only=false -- no .gitmodules entry for %s" % SUBMODULE_PATH
    )


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_has_non_gitlink_follows_the_two_greps(tmp_path) -> None:
    del tmp_path
    gitlink = ":160000 160000 aaa bbb M\tprivate/x"
    blob = ":100644 100644 aaa bbb M\treadme.md"
    assert port.has_non_gitlink("") is False, "an empty herestring is one empty line"
    assert port.has_non_gitlink(gitlink) is False
    assert port.has_non_gitlink(blob) is True
    assert port.has_non_gitlink(gitlink + "\n" + blob) is True
    assert port.has_non_gitlink(gitlink + "\n" + gitlink) is False
    # THE `-r` CASE THE TWIN'S COMMENT NAMES: without it a nested gitlink change reports as its parent tree, which is NOT the gitlink prefix and therefore reads as a real change.
    assert port.has_non_gitlink(":040000 040000 aaa bbb M\tprivate") is True


def test_awk_field_matches_awks_default_splitting() -> None:
    meta = ":160000 160000 aaa bbb M"
    assert port.awk_field(meta, 3) == "aaa"
    assert port.awk_field(meta, 4) == "bbb"
    assert port.awk_field("  a   b  ", 1) == "a", "leading and interior runs collapse"
    assert port.awk_field("a b", 9) == "", "a field past the end prints empty"
    assert port.awk_field("", 1) == ""


def test_read_tab_pair_matches_ifs_tab_read() -> None:
    assert port.read_tab_pair(":160000 160000 a b M\tprivate/x") == (
        ":160000 160000 a b M",
        "private/x",
    )
    assert port.read_tab_pair("") == ("", "")
    assert port.read_tab_pair("only-one-field") == ("only-one-field", "")
    assert port.read_tab_pair("a\t\tb") == ("a", "b"), "tab is IFS whitespace, so a run is one"


def test_short_is_a_substring_not_a_git_call() -> None:
    assert port.short("1234567890") == "1234567"
    assert port.short("abc") == "abc", "a short value is not padded and does not fail"
    assert port.short("") == ""


def test_submodule_key_and_the_suffix_strip() -> None:
    lines = "submodule.private/x.path private/x\nsubmodule.private/y.path private/y"
    assert port.submodule_key(lines, "private/y") == "submodule.private/y.path"
    assert port.submodule_key(lines, "private/z") == ""
    assert port.strip_path_suffix("submodule.private/x.path") == "submodule.private/x"
    assert port.strip_path_suffix("no-suffix") == "no-suffix"


def test_at_least_one_is_bash_arithmetic_including_the_fatal_rows() -> None:
    """EVERY ROW PROBED AGAINST REAL BASH. The last group is DEFECT D."""
    assert port._at_least_one("1") is True
    assert port._at_least_one("2") is True
    assert port._at_least_one("0") is False
    assert port._at_least_one("") is False
    assert port._at_least_one("   ") is False
    assert port._at_least_one("-1") is False
    assert port._at_least_one("010") is True, "octal 8"
    assert port._at_least_one("0x10") is True, "hex 16"
    assert port._at_least_one("08") is False, "a malformed octal is false, not fatal"
    assert port._at_least_one("1a") is False, "a bad number, not a variable"

    for fatal, name in (("null", "null"), ("a b", "a"), ("a-b", "a")):
        with pytest.raises(port.BashUnboundError) as caught:
            port._at_least_one(fatal)
        assert caught.value.name == name


def test_the_bash_diagnostic_normaliser_keeps_the_message() -> None:
    """A NORMALISER THAT SWALLOWED MORE WOULD MAKE `_agree` VACUOUS on the one
    path that uses it."""
    bash_side = "/x/.ci/scripts/ci/detect-pointer-bump.sh: line 154: null: unbound variable"
    port_side = "detect-pointer-bump.sh: null: unbound variable"
    assert _mask(bash_side) == _mask(port_side)
    assert _mask(bash_side) == "detect-pointer-bump: null: unbound variable"
    other = "/x/.ci/scripts/ci/detect-pointer-bump.sh: line 154: other: unbound variable"
    assert _mask(other) != _mask(bash_side)
    assert _mask("✓ pointer_bump_only=false -- x") == "✓ pointer_bump_only=false -- x"


def test_the_port_carries_no_gate_header() -> None:
    """Neither file declares a gate, and the twin is checked in the same breath
    so "neither has one" cannot be satisfied by a broken matcher."""
    open_marker = re.compile(r"^\s*(?:#|//|\*)?\s*-{2,}\s*gate\s*-{2,}\s*$")
    for path in (TWIN, PORT_FILE):
        assert [
            ln for ln in path.read_text(encoding="utf-8").split("\n") if open_marker.match(ln)
        ] == [], path


def test_the_environment_this_module_reads_is_read_with_literal_keys() -> None:
    """`check:ci-python-env-registry` derives a module's inputs by walking the
    AST for literal `os.environ` reads, so a read through a local alias would be invisible and the module would report zero inputs while depending on six.

    THE LIST IS THE TWIN'S OWN HEADER, in its order."""
    source = PORT_FILE.read_text(encoding="utf-8")
    for name in (
        "GITHUB_EVENT_NAME",
        "GITHUB_REPOSITORY",
        "CHECKS_TOKEN",
        "GITHUB_PAT",
        "GITHUB_STEP_SUMMARY",
        "GITHUB_EVENT_PATH",
    ):
        assert 'os.environ.get("%s"' % name in source, name
        assert name in TWIN.read_text(encoding="utf-8"), name


def test_the_twin_still_says_what_this_port_says_it_says() -> None:
    text = TWIN.read_text(encoding="utf-8")
    assert "WALK_CAP=5" in text
    assert "--deepen=$((WALK_CAP + 1))" in text
    assert "grep -vE '^:160000 160000 '" in text
    assert 'net=$(git diff-tree -r --raw "$baseline" HEAD)' in text, "DEFECT B's line"
    assert "head_sha=$(git rev-parse HEAD)" in text, "DEFECT A's line"
    assert "identical | ahead" in text
    assert port.REPO_SLUG_SED in text
    assert port.HEAD_SHA_JQ in text
    assert port.GREEN_JQ in text


def test_the_helpers_the_selftest_leans_on_are_exported() -> None:
    for name in (
        "has_non_gitlink",
        "awk_field",
        "read_tab_pair",
        "short",
        "submodule_key",
        "strip_path_suffix",
        "find_baseline",
        "repo_slug",
    ):
        assert inspect.isfunction(getattr(port, name)), name
