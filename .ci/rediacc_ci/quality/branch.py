"""Report whether a PR branch is behind its base, and whether a rebase would conflict.

Ported from `.ci/scripts/quality/check-branch.sh`, which W7 P5 batch G2 retired once `.ci/shadow/w7p2-branch.observations.jsonl` asserted equivalence over five distinct trees and the twin's own text was recorded as goldens.

DETECTION ONLY. This module never rewrites history, never moves a ref, and never publishes anything. The twin's header says why, and it is the reason the gate has the shape it has:

    WHY IT ONLY REPORTS. It used to `git rebase origin/<base>` and then republish
    the branch from CI, so the bot rewrote contributors' branches out from under
    them (observed: "rediacc-ci-cd Bot force-pushed the 0827-1 branch"). That
    required a contents:write app token in a job whose code comes from the PR
    itself, and it rewrote a real checkout that other work may be sitting in.
    The rebase is now the operator's, run locally where the tooling for it lives
    (/branch-rebase and the worklist --git verbs); CI's job is to say that a
    rebase is needed, not to perform one.

    Usage:
      .ci/scripts/quality/check-branch.sh

    Environment variables:
      GITHUB_BASE_REF - Base branch name (e.g., 'main') - set by GitHub Actions
      GITHUB_HEAD_REF - PR branch name (optional; only used to name the branch in
                        the printed recipe) - set by GitHub Actions
      GITHUB_EVENT_NAME - GitHub event type (e.g., 'pull_request')

    Exit codes:
      0 - Branch is up-to-date with the base (or this is not a pull request)
      1 - Branch is behind the base and must be rebased locally. The message
          separates the two cases the probe can tell apart:
            - Branch has conflicts  -> resolve them during the local rebase
            - no conflicts detected -> a plain local rebase is enough
          Exit 1 is also how an UNANSWERABLE check reports itself: if the
          behind-count cannot be computed the branch must not be called current.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE FETCH REFSPEC IS SPELLED OUT, and the twin's paragraph explaining it is carried at the call site because it is the kind of line a tidy-up deletes:

    AN EXPLICIT REFSPEC, because every line below reads `origin/${BASE_BRANCH}`
    and a bare `git fetch origin <branch>` does not promise to write it. The
    remote-tracking ref is updated only when the fetched ref matches
    remote.origin.fetch, and actions/checkout configures that narrowly in some
    shapes -- proven both directions in scripts/gates/check-pr-task-trailers.ts's
    selftest, where a bare fetch under a narrow refspec leaves origin/main absent
    while the explicit form creates it. This works today because the checkout
    above names a branch; spelling it out means it keeps working if that changes.

A FAILED FETCH TAKES THE GATE DOWN WITH GIT'S OWN WORDS, in both implementations. The twin runs the fetch under `set -e` with stderr inherited, so a missing remote ref prints `fatal: couldn't find remote ref ...` and the gate exits with git's status. This module does the same, deliberately: forging a friendlier message would replace git's diagnostic, which is the only text that
says WHICH ref was missing, and a port that summarised it would be caught by the differential anyway. It is also the reason `run_git` here inherits stderr rather than capturing it.

THE `|| echo "0"` THAT USED TO END THE REV-LIST IS THE BUG THIS GATE CARRIES A SCAR FROM, and the twin's words are kept verbatim at the branch:

    FAIL LOUDLY. This used to end in `|| echo "0"`, and 0 is the same value the
    gate reads as "up-to-date" two lines down, where it exits 0. So a missing
    origin ref, a shallow clone with no merge base, or any other rev-list failure
    reported the branch as current and let the merge proceed. The fetch above has
    to have succeeded for the ref to exist, so a failure here is a real breakage.

`git merge-tree --write-tree` IS A PROBE, NOT A PROOF, and the twin's own reading of it is carried at the case statement: exit 0 clean, exit 1 conflicts, anything
else means the probe itself could not run (e.g. unrelated histories), which is
reported as UNKNOWN rather than silently as clean. Measured while porting: a `--orphan` branch against a populated base gives exit 128 and `fatal: refusing to merge unrelated histories`, which is the third arm and is therefore exercised by the differential rather than reasoned about.

THE THIRD ARM'S DETAIL LINES GO TO STDERR AND ARE THEREFORE FINDINGS. The twin writes `sed 's/^/ /' "$MERGE_TREE_OUT" >&2` under a `log_warn`, so the indented git diagnostic attaches to the warning above it. The conflict arm's detail lines go to STDOUT under an `echo`, where nothing is carrying them, so they are progress rather than findings. That asymmetry is the twin's and is
reproduced stream for stream; moving either one would change what the gate is understood to be objecting to.

`git log --oneline ... | head -5` IS FIVE LINES, NOT A SIGPIPE DANCE. The twin runs it under `set -o pipefail`, which in principle means `head` exiting early could make the pipeline report 141 and abort the gate. Measured on a fixture eight commits behind: the producer finishes into the 64 KB pipe buffer long before `head` closes it, so the shape never fires at these sizes. It is
named here because the same shape DID fire in check-ci-watch-recipe.sh, where the producer was megabytes; the port takes the first five lines and cannot race.

THE PRINTED RECIPE IS DATA, NOT DECORATION. Sixteen lines of it name `/branch-rebase` and three `worklist.py --git` verbs. It is carried byte for byte, on stdout, because a reader following it is the whole point of the gate exiting 1 rather than rebasing anything itself.
"""

import os
import pathlib
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The event this gate is about. Anything else is not a pull request and the gate says so and exits 0, which is a SKIP and not a pass: there is no branch to be behind when nothing is proposing a merge.
PR_EVENT = "pull_request"

# The base branch when GitHub does not name one. `main`, matching the twin.
DEFAULT_BASE = "main"

# How many of the base's commits are echoed back, and how many merge-tree stage lines. Both are the twin's numbers; they are display limits, not thresholds, so a change here changes what a human reads and nothing the gate decides.
RECENT_COMMITS = 5
CONFLICT_LINES = 20


def run_git(args: list[str], root: pathlib.Path, capture_stderr: bool = True):
    """`git <args>` in `root`. Returns the CompletedProcess.

    `capture_stderr=False` INHERITS stderr, which is what the fetch needs: git's
    own diagnostic is the only text that says which ref was missing, and the twin lets it through untouched.
    """
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if capture_stderr else None,
        check=False,
    )


def fetch_refspec(base: str) -> str:
    """`+refs/heads/<base>:refs/remotes/origin/<base>`, the explicit form.

    A function rather than an inline f-string so the selftest can assert the shape without running a fetch: the whole point of the twin's paragraph is that a bare `git fetch origin <branch>` is NOT this, and the difference is one line nobody re-reads.
    """
    return "+refs/heads/%s:refs/remotes/origin/%s" % (base, base)


def indent(text: str, width: int = 4) -> list[str]:
    """`sed 's/^/ /'` over a captured stream, as a list of lines.

    The trailing newline is dropped the way sed's line-oriented reading does, so an output ending in `\\n` does not produce a final line of four spaces.
    """
    if text == "":
        return []
    body = text.removesuffix("\n")
    return [" " * width + line for line in body.split("\n")]


# The rebase recipe, exactly as the twin echoes it. A tuple of lines rather than one triple-quoted string, because the twin interpolates the base branch into two of them and a single blob would hide which.
def recipe(base: str, head: str) -> list[str]:
    """The sixteen-line REBASE LOCALLY block, in the twin's order and spacing.

    `${HEAD_BRANCH:+ (branch: X)}` is bash's "expand only if non-empty", so an
    unset GITHUB_HEAD_REF prints the banner with no parenthetical at all rather than an empty one. Carried, because a `(branch: )` in a CI log reads as a bug in the gate.
    """
    suffix = " (branch: %s)" % head if head else ""
    return [
        "",
        "==============================================",
        "REBASE LOCALLY%s" % suffix,
        "==============================================",
        "",
        "  /branch-rebase %s" % base,
        "",
        "    Rebases the console repo AND every submodule carrying a branch of the",
        "    same name, resolving the gitlink conflicts that a plain 'git rebase'",
        "    gets wrong. It rebases and verifies only; it lands nothing.",
        "",
        "  If the rebase halts on a conflict:",
        "",
        "    .claude/hooks/stop/worklist.py --git rebase-resolve",
        "        reports where it stopped and stages the paths it can decide",
        "        (gitlinks by ancestry, registry unions). All-or-nothing: if any",
        "        path needs you, nothing is written.",
        "    .claude/hooks/stop/worklist.py --git rebase-continue --execute",
        "        continues the rebase once every conflicted path is staged.",
        "",
        "  Prove no commit was lost across the rebase:",
        "",
        "    .claude/hooks/stop/worklist.py --git snapshot > /tmp/pre.snap   # BEFORE",
        "    .claude/hooks/stop/worklist.py --git verify-rebase /tmp/pre.snap origin/%s" % base,
        "",
        "==============================================",
    ]


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 up-to-date or not a PR, 1 behind or unanswerable.

    `--selftest` is intercepted BEFORE the fetch, so the controls never touch a remote.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()

    # Skip check for non-PR events
    if os.environ.get("GITHUB_EVENT_NAME", "") != PR_EVENT:
        log.info("Skipping branch check (not a pull request)")
        return 0

    base = os.environ.get("GITHUB_BASE_REF") or DEFAULT_BASE
    head = os.environ.get("GITHUB_HEAD_REF", "")

    log.step("Checking branch status against origin/%s..." % base)

    # Fetch the base branch to ensure we have latest. See the port notes for the twin's paragraph on why the refspec is explicit.
    log.info("Fetching origin/%s..." % base)
    fetched = run_git(
        ["fetch", "origin", fetch_refspec(base), "--quiet"], root, capture_stderr=False
    )
    if fetched.returncode != 0:
        # The twin runs this under `set -e`, so git's own diagnostic is the message and git's status is the gate's. Reproduced rather than improved: see the port notes.
        return fetched.returncode

    # Check 1: Is the PR behind the base branch?
    #
    # FAIL LOUDLY. This used to end in `|| echo "0"`, and 0 is the same value the gate reads as "up-to-date" two lines down, where it exits 0. So a missing origin ref, a shallow clone with no merge base, or any other rev-list failure reported the branch as current and let the merge proceed.
    counted = run_git(["rev-list", "--count", "HEAD..origin/%s" % base], root)
    if counted.returncode != 0:
        log.error("git rev-list failed for HEAD..origin/%s (exit %d)" % (base, counted.returncode))
        for line in indent(counted.stderr.decode("utf-8", "replace")):
            print(line, file=sys.stderr)
        log.error(
            "Cannot tell whether this branch is behind %s, so it must not be reported "
            "as up-to-date." % base
        )
        return 1

    behind = counted.stdout.decode("utf-8", "replace").strip()

    if behind == "0":
        log.info("Branch is up-to-date with origin/%s" % base)
        return 0

    log.warn("Branch is %s commit(s) behind origin/%s" % (behind, base))
    print()
    print("Recent commits on %s not in this branch:" % base)
    recent = run_git(["log", "--oneline", "HEAD..origin/%s" % base], root)
    for line in recent.stdout.decode("utf-8", "replace").split("\n")[:RECENT_COMMITS]:
        if line != "":
            print(line)
    print()

    # Check 2: would rebasing conflict?
    #
    # `git merge-tree --write-tree` answers this WITHOUT touching the working tree, the index, HEAD, or any ref -- it writes only loose objects into the object database. That is the whole reason it replaced the in-place `git rebase` that used to live here: this job's checkout is a real tree, and a gate has no business rewriting one.
    #
    # It is a THREE-WAY MERGE probe, not a replay of each commit, so read it as an indication and not a proof: a merge that resolves cleanly can still stop
    # a per-commit rebase, and vice versa. Exit 0 = clean, 1 = conflicts,
    # anything else = the probe itself could not run (e.g. unrelated histories),
    # which is reported as unknown rather than silently as "clean".
    log.step("Probing whether a rebase onto origin/%s would conflict..." % base)

    probe = subprocess.run(
        ["git", "merge-tree", "--write-tree", "origin/%s" % base, "HEAD"],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    probe_out = probe.stdout.decode("utf-8", "replace")

    if probe.returncode == 0:
        log.info("No conflicts detected - a plain rebase should apply cleanly")
    elif probe.returncode == 1:
        log.error("Branch has conflicts: rebasing onto origin/%s needs manual resolution" % base)
        print()
        print("Conflicting paths (merge-tree stage entries):")
        # Line 1 is the toplevel tree oid; the conflict report follows it.
        tail = probe_out.split("\n")[1:]
        if tail and tail[-1] == "":
            tail = tail[:-1]
        for line in indent("\n".join(tail))[:CONFLICT_LINES]:
            print(line)
        print()
    else:
        log.warn(
            "Conflict probe could not run (git merge-tree exit %d); reporting as unknown"
            % probe.returncode
        )
        for line in indent(probe_out):
            print(line, file=sys.stderr)
        print()

    log.error("This branch must be rebased before it can merge. CI does not do it for you.")
    for line in recipe(base, head):
        print(line)

    return 1


# --------------------------------------------------------------------------- Selftest ---------------------------------------------------------------------------


def _git(root: pathlib.Path, *args: str) -> None:
    """A quiet git for fixture construction. Raises on failure, on purpose.

    A fixture that half-built is worse than no fixture: every assertion below it would then be measuring a repository nobody described.
    """
    subprocess.run(
        ["git", *args],
        cwd=str(root),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _fixture(root: pathlib.Path, *, behind: int, conflict: bool) -> pathlib.Path:
    """A repository whose HEAD is `behind` commits behind its own `main`.

    `origin` is the repository ITSELF (`git remote add origin .`), which is not a trick: the gate only ever reads `refs/remotes/origin/<base>`, and fetching a local branch into that namespace produces exactly the state a real PR checkout has. It also keeps the fixture self-contained, so no assertion here depends on a second directory that a reader cannot see.
    """
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main", ".")
    _git(root, "config", "user.email", "gate@example.invalid")
    _git(root, "config", "user.name", "gate")
    (root / "shared.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "-A", "--", ".")
    _git(root, "commit", "-qm", "base")
    _git(root, "checkout", "-qb", "feature")
    (root / "feature.txt").write_text("feature\n", encoding="utf-8")
    if conflict:
        # The SAME file both sides edit, which is what makes merge-tree exit 1.
        (root / "shared.txt").write_text("feature side\n", encoding="utf-8")
    _git(root, "add", "-A", "--", ".")
    _git(root, "commit", "-qm", "feature work")
    _git(root, "checkout", "-q", "main")
    for i in range(behind):
        (root / "shared.txt").write_text("base %d\n" % i, encoding="utf-8")
        _git(root, "add", "-A", "--", ".")
        _git(root, "commit", "-qm", "base commit %d" % i)
    _git(root, "checkout", "-q", "feature")
    _git(root, "remote", "add", "origin", ".")
    return root


def _run(root: pathlib.Path, **env: str) -> int:
    """Drive `main([])` against `root` with a controlled environment.

    Every GITHUB_* variable is set or removed explicitly, because a developer machine can carry one from a previous shell and the whole gate branches on the first of them.
    """
    keys = ("GITHUB_EVENT_NAME", "GITHUB_BASE_REF", "GITHUB_HEAD_REF", paths.ROOT_ENV)
    saved = {k: os.environ.get(k) for k in keys}
    try:
        for key in keys:
            os.environ.pop(key, None)
        os.environ[paths.ROOT_ENV] = str(root)
        for key, value in env.items():
            os.environ[key] = value
        return main([])
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def selftest() -> int:
    """Both directions for every arm, over real repositories built by construction.

    A gate that only proved "behind reds" would pass with the up-to-date arm deleted, so each red below has a green beside it: behind against level, conflicting against clean, unrelated against related, PR against non-PR.
    """
    ctl = Controls("branch", floor=16, verbose=True)

    # -- the pure helpers ---------------------------------------------------
    ctl.check(
        "the refspec is the EXPLICIT form, not a bare branch name",
        fetch_refspec("main"),
        "+refs/heads/main:refs/remotes/origin/main",
    )
    ctl.falsy(
        "the refspec is not the bare form the twin's paragraph warns about",
        fetch_refspec("main") == "main",
    )
    ctl.check("indent prefixes four spaces", indent("a\nb"), ["    a", "    b"])
    ctl.check(
        "indent drops the trailing newline rather than emitting a blank line",
        indent("a\n"),
        ["    a"],
    )
    ctl.check("indent of nothing is nothing", indent(""), [])
    ctl.truthy(
        "the recipe names the base branch in the /branch-rebase line",
        "  /branch-rebase release" in recipe("release", ""),
    )
    ctl.truthy(
        "the recipe names the head branch when there is one",
        "REBASE LOCALLY (branch: feat-1)" in recipe("main", "feat-1"),
    )
    ctl.check(
        "the recipe prints NO parenthetical when the head branch is unset",
        "REBASE LOCALLY" in recipe("main", ""),
        True,
    )
    ctl.falsy(
        "and does not print an empty one",
        "REBASE LOCALLY (branch: )" in recipe("main", ""),
    )

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        level = _fixture(base / "level", behind=0, conflict=False)
        ctl.check(
            "MIRROR: an up-to-date branch exits 0",
            _run(level, GITHUB_EVENT_NAME=PR_EVENT, GITHUB_BASE_REF="main"),
            0,
        )
        ctl.check(
            "MIRROR: a non-PR event skips and exits 0 without fetching",
            _run(level, GITHUB_EVENT_NAME="push"),
            0,
        )

        clean = _fixture(base / "clean", behind=2, conflict=False)
        ctl.check(
            "PLANT: a branch two commits behind reds",
            _run(clean, GITHUB_EVENT_NAME=PR_EVENT, GITHUB_BASE_REF="main"),
            1,
        )

        clashing = _fixture(base / "clash", behind=2, conflict=True)
        ctl.check(
            "PLANT: a branch behind AND conflicting reds",
            _run(clashing, GITHUB_EVENT_NAME=PR_EVENT, GITHUB_BASE_REF="main"),
            1,
        )
        # The probe itself, driven directly, so the three arms are told apart rather than inferred from one exit code.
        probe = subprocess.run(
            ["git", "merge-tree", "--write-tree", "origin/main", "HEAD"],
            cwd=str(clashing),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        ctl.check("CONTROL: merge-tree reports conflicts as exit 1", probe.returncode, 1)
        probe = subprocess.run(
            ["git", "merge-tree", "--write-tree", "origin/main", "HEAD"],
            cwd=str(clean),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        ctl.check("CONTROL: merge-tree reports a clean merge as exit 0", probe.returncode, 0)

        # THE THIRD ARM. An orphan branch has no common ancestor with main, so the probe cannot run at all and must be reported as unknown rather than as clean. Measured while porting: exit 128, "fatal: refusing to merge unrelated histories".
        orphan = _fixture(base / "orphan", behind=2, conflict=False)
        _git(orphan, "checkout", "-q", "--orphan", "unrelated")
        _git(orphan, "rm", "-rqf", ".")
        (orphan / "only.txt").write_text("only\n", encoding="utf-8")
        _git(orphan, "add", "-A", "--", ".")
        _git(orphan, "commit", "-qm", "unrelated root")
        # ORDER MATTERS HERE, and getting it wrong is instructive. Probing BEFORE the gate has fetched leaves `origin/main` unresolvable, and `git merge-tree` then exits 1 with "not something we can merge" -- which the twin's case statement reads as CONFLICTS, not as unknown. The real flow always fetches first, so the twin is never in that state; the control below runs the gate
        # first for the same reason.
        ctl.check(
            "PLANT: an unrelated history still reds rather than reporting clean",
            _run(orphan, GITHUB_EVENT_NAME=PR_EVENT, GITHUB_BASE_REF="main"),
            1,
        )
        probe = subprocess.run(
            ["git", "merge-tree", "--write-tree", "origin/main", "HEAD"],
            cwd=str(orphan),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        ctl.truthy(
            "CONTROL: unrelated histories are neither 0 nor 1 (the unknown arm)",
            probe.returncode not in (0, 1),
        )
        ctl.truthy(
            "CONTROL: and the unknown arm carries git's own words",
            b"refusing to merge unrelated histories" in probe.stdout,
        )

        # A BASE BRANCH THAT DOES NOT EXIST is git's failure, not the gate's, and the gate must not survive it: exit 0 here would be the `|| echo "0"` defect wearing a different hat.
        ctl.truthy(
            "PLANT: a missing base ref exits non-zero with git's own status",
            _run(clean, GITHUB_EVENT_NAME=PR_EVENT, GITHUB_BASE_REF="no-such-branch") != 0,
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
