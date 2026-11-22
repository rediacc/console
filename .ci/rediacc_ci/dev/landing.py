"""`./run.sh worktree landing`: the one landing tree, a sibling of the main checkout, on the open PR's branch (PLAN-two-track-merge-dev LT2).

The tree sits at `<dirname of the main checkout>/<basename>-landing`. It is no lease: it lives outside `.claude/worktrees`, holds a branch rather than a detached HEAD, and takes no writer-cap slot or pin. Each submodule tree holds a branch of the same name, made at the gitlink when absent. The binding record, `rediacc-landing.json` in the common git dir, names the tree and the branch.

Only the last stdout line is data: the tree's absolute path. Everything else goes to stderr.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.core import gh_retry
from rediacc_ci.dev import landing_promote
from rediacc_ci.dev import worktree_lease as lease
from rediacc_ci.dev import worktree_spike as spike

SUFFIX = "-landing"
REASON = "landing"
GH_TIMEOUT = 60

LANDING_HELP = """\
Usage: ./run.sh worktree landing [--promote]

Make, or reuse, the landing tree: a sibling of the main checkout named
<checkout>-landing, on the open PR's MMDD-N branch, with each submodule tree on
a branch of the same name and dependencies seeded. Re-running fetches and
fast-forwards it. The last stdout line is the tree's absolute path.

Refused: main, a branch the main checkout holds, another MMDD-N branch checked
out in the main checkout, a second path, and a dirty tree. The main checkout
must be off the PR branch, since git holds one branch in one tree. A landing
tree sitting on main or a detached HEAD after the merge is not refreshed: the
exit is --promote.
"""


class LandingRefusedError(RuntimeError):
    """The landing tree was not made or reused, and the message says why."""


def run_gh(args, cwd):
    """`(rc, stdout)` of `gh <args>`; 127 when gh is absent. A transient 5xx or connection fault is retried (gh_retry); a 4xx fails at once."""
    try:
        done = gh_retry.retry_transient(
            lambda: subprocess.run(
                ["gh", *args],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
                timeout=GH_TIMEOUT,
            ),
            lambda r: None if r.returncode == 0 else r.stderr or "failed",
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return done.returncode, done.stdout


def landing_path(root):
    root = pathlib.Path(root)
    return root.parent / (root.name + SUFFIX)


def _policy():
    return spike.load_commit_policy()


def write_record(root, path, branch):
    """Bind `path` to `branch` through `commit_policy.write_landing_record`, the one writer of the record (`rediacc-landing.json` in the common git dir)."""
    return _policy().write_landing_record(str(root), str(path), branch)


def _shape():
    return _policy().BRANCH_SHAPE


def _open_pr_branches(root, gh):
    rc, text = gh(
        ["pr", "list", "--state", "open", "--author", "@me", "--json", "headRefName"], root
    )
    # A gh that cannot answer is named as such, never read as "no open PR" (review finding 2623001e.3): the refusal that followed blamed the checkout.
    if rc != 0:
        message = "gh pr list failed (rc %d), so the open PR's branch is unknown" % rc
        raise LandingRefusedError(message)
    try:
        rows = json.loads(text or "[]")
    except ValueError as exc:
        message = "gh pr list printed no JSON (%s), so the open PR's branch is unknown" % exc
        raise LandingRefusedError(message) from exc
    if not isinstance(rows, list):
        message = "gh pr list printed %s, not a list" % type(rows).__name__
        raise LandingRefusedError(message)
    shape = _shape()
    return sorted(
        {
            r["headRefName"]
            for r in rows
            if isinstance(r, dict) and shape.match(r.get("headRefName", ""))
        }
    )


def choose_branch(root, gh):
    """The open PR's branch, else the main checkout's own branch, refusing `main`, a second PR branch and a development branch other than the PR's."""
    shape = _shape()
    current = spike.out(root, "symbolic-ref", "-q", "--short", "HEAD")
    prs = _open_pr_branches(root, gh)
    if len(prs) > 1:
        message = "several open PR branches (%s), so no single landing branch" % ", ".join(prs)
        raise LandingRefusedError(message)
    branch = prs[0] if prs else current
    if branch == lease.BASE_BRANCH or not shape.match(branch or ""):
        message = (
            "no open PR branch: %r is not an MMDD-N branch, and the landing tree never holds main"
            % branch
        )
        raise LandingRefusedError(message)
    # The main checkout on another MMDD-N branch is the two-tree shape itself (the development branch, stacked on the PR's): it is returned, never refused.
    if current == branch and not prs:
        # No open PR, so the landing branch is the main checkout's own (review finding 2623001e.4): the advice names what to cut, not the branch already held.
        message = (
            "no open PR, so the landing branch is the main checkout's own %s, and git keeps one "
            "branch in one tree: cut or switch to another MMDD-N branch (the development "
            "branch) in the main checkout first" % branch
        )
        raise LandingRefusedError(message)
    # current == branch with an open PR: the first switch-over, which make_landing runs (`_switch_over`).
    return branch


def _listed(root):
    found = set()
    for line in spike.must(root, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            found.add(os.path.realpath(line[len("worktree ") :]))
    return found


def _dirty(tree):
    return spike.out(tree, "status", "--porcelain", "--ignore-submodules=none")


def _has_ref(cwd, ref):
    return spike.git(cwd, "rev-parse", "--verify", "-q", ref).returncode == 0


def _fast_forward(tree, branch, label):
    fetched = spike.git(tree, "fetch", "origin", branch)
    if fetched.returncode != 0:
        message = "git fetch origin %s failed in %s: %s" % (branch, label, fetched.stderr.strip())
        raise LandingRefusedError(message)
    merged = spike.git(tree, "merge", "--ff-only", "FETCH_HEAD")
    if merged.returncode != 0:
        message = "%s is not a fast-forward of origin/%s: git -C %s rebase origin/%s" % (
            label,
            branch,
            tree,
            branch,
        )
        raise LandingRefusedError(message)


def _guard_path(root, path):
    """Refuse a second path and a foreign directory; True when the tree already exists and is this repository's."""
    record, problem = _policy().read_landing_record(str(root))
    if problem:
        message = "the landing record binds nothing (%s): remove it to bind %s" % (problem, path)
        raise LandingRefusedError(message)
    if record and os.path.realpath(record["path"]) != os.path.realpath(path):
        message = "the landing tree is bound to %s, so no second path %s" % (record["path"], path)
        raise LandingRefusedError(message)
    if not os.path.lexists(path):
        return False
    if os.path.realpath(path) not in _listed(root):
        message = "%s exists and is not a worktree of this repository" % path
        raise LandingRefusedError(message)
    return True


def _refuse_on_main(path):
    """Refuse while the landing tree sits on main or a detached HEAD (a hotfix after the merge, PLAN-simple-two-tree-loop ruling 10): it is not refreshed there, and the exit is promote."""
    held = spike.out(path, "symbolic-ref", "-q", "--short", "HEAD")
    if held in ("", lease.BASE_BRANCH):
        message = (
            "the landing tree %s sits on %s (after a merge a hotfix may run there), so it "
            "is not refreshed: the exit is `./run.sh worktree landing --promote` from the main "
            "checkout once the release is green" % (path, held or "a detached HEAD")
        )
        raise LandingRefusedError(message)
    return held


def _reuse(path, branch):
    held = _refuse_on_main(path)
    if held != branch:
        message = "the landing tree is on %r, not the open PR's %s: git -C %s switch %s" % (
            held,
            branch,
            path,
            branch,
        )
        raise LandingRefusedError(message)
    if _dirty(path):
        message = "the landing tree %s is dirty: commit or discard its changes first" % path
        raise LandingRefusedError(message)
    _fast_forward(path, branch, str(path))
    for sub, sha in lease.gitlinks_at(path, "HEAD"):
        tree = path / sub
        # A missing submodule tree refuses (review finding 2623001e.2): a reuse that skipped it reported success with the dependency absent.
        if not tree.is_dir() or not (tree / ".git").exists():
            message = "the landing tree %s lacks its submodule tree %s, so it is incomplete" % (
                path,
                sub,
            )
            raise LandingRefusedError(message)
        if spike.out(tree, "rev-parse", "HEAD") == sha:
            continue
        if _dirty(tree):
            message = "the submodule tree %s is dirty" % tree
            raise LandingRefusedError(message)
        merged = spike.git(tree, "merge", "--ff-only", sha)
        if merged.returncode != 0:
            message = "%s cannot fast-forward to its gitlink %s: git -C %s rebase %s" % (
                sub,
                sha,
                tree,
                sha,
            )
            raise LandingRefusedError(message)


def _tip_of(root, branch):
    if _has_ref(root, "refs/heads/%s" % branch):
        return spike.must(root, "rev-parse", "refs/heads/%s" % branch), True
    # A failed fetch refuses, as `_fast_forward` does: a stale `refs/remotes/origin/<branch>` is no tip to build on (review finding 2623001e.1).
    fetched = spike.git(root, "fetch", "origin", branch)
    if fetched.returncode != 0:
        message = "git fetch origin %s failed: %s" % (branch, fetched.stderr.strip())
        raise LandingRefusedError(message)
    return spike.out(root, "rev-parse", "refs/remotes/origin/%s" % branch), False


def _add_console(root, path, branch, local):
    lock = ("--lock", "--reason", REASON)
    if local:
        spike.must(root, "worktree", "add", *lock, str(path), branch)
    else:
        spike.must(root, "worktree", "add", *lock, "-b", branch, str(path), "origin/%s" % branch)


def _add_sub(store, tree, branch, sha):
    lock = ("--lock", "--reason", REASON)
    if _has_ref(store, "refs/heads/%s" % branch):
        spike.must(store, "worktree", "add", *lock, str(tree), branch)
    else:
        # A submodule the PR does not touch has no branch of that name, and creating one would add a live branch it never pushes (and the git-level hook, run from the module store, refuses it as a cut off main): its tree sits detached at the gitlink, as a lease's does.
        spike.must(store, "worktree", "add", *lock, "--detach", str(tree), sha)


def _rollback(root, repo, path):
    for store, tree in (
        *((repo.store(sub), path / sub) for sub in repo.submodules),
        (root / ".git", path),
    ):
        spike.git(store, "worktree", "unlock", str(tree))
        spike.git(store, "worktree", "remove", "--force", str(tree))
        spike.git(store, "worktree", "prune")
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _create(root, path, branch, seed):
    tip, local = _tip_of(root, branch)
    if not tip:
        message = "branch %s is on neither this clone nor origin" % branch
        raise LandingRefusedError(message)
    held = lease.gitlinks_at(root, tip)
    absent = sorted(sub for sub, _ in held if lease._store_of(root, sub) is None)
    if absent:
        message = "no module store for %s: git submodule update --init -- %s" % (
            ", ".join(absent),
            " ".join(absent),
        )
        raise LandingRefusedError(message)
    repo = spike.Repo(root, [sub for sub, _ in held])
    try:
        _add_console(root, path, branch, local)
        for sub, sha in held:
            _add_sub(repo.store(sub), path / sub, branch, sha)
        seed(path, root, tip)
        write_record(root, path, branch)
    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
        spike.InterruptedRunError,
    ) as exc:
        _rollback(root, repo, path)
        message = "landing tree not made: %s" % exc
        raise LandingRefusedError(message) from exc


def _give_back(trees, branch):
    """Switch each of `trees` back to `branch` and return the trees where that failed (named, never silent)."""
    stuck = []
    for tree in trees:
        back = spike.git(tree, "switch", "--quiet", branch)
        if back.returncode != 0:
            log.warn("could not switch %s back to %s: %s" % (tree, branch, back.stderr.strip()))
            stuck.append(str(tree))
    return stuck


def _undo_landing(root, path, branch):
    """Remove a landing tree this run made, its submodule trees and its record."""
    tip, _local = _tip_of(root, branch)
    held = lease.gitlinks_at(root, tip) if tip else []
    _rollback(root, spike.Repo(root, [sub for sub, _ in held]), path)
    (root / ".git" / "rediacc-landing.json").unlink(missing_ok=True)


def _switch_over(root, path, branch, seed, next_name, today):
    """The first switch-over: the main checkout holds the open PR's `branch`, so it hands that branch to a new landing tree and cuts the next MMDD-N here, stacked on it (operator ruling ASKED:2026-11-20T18:46Z).

    Order matters to the git-level hooks: the main checkout and its submodule trees detach, the landing tree is made on `branch` and the record written, then the console cuts first (a submodule branch carries the console's name) at `branch`'s tip, which `reference-transaction` admits as the stacked cut, then each submodule tree that held `branch` cuts at its own HEAD.
    """
    try:
        cut = (next_name or landing_promote._default_next_name)(
            root, today or landing_promote._today()
        )
    except (OSError, RuntimeError) as exc:
        message = "the next branch name could not be read, so nothing moved: %s" % exc
        raise LandingRefusedError(message) from exc
    subs = [
        sub
        for sub in landing_promote._submodule_trees(root).values()
        if spike.out(sub, "symbolic-ref", "-q", "--short", "HEAD") == branch
    ]
    detached = []
    try:
        for tree in (*subs, root):
            spike.must(tree, "switch", "--quiet", "--detach")
            detached.append(tree)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        _give_back(detached, branch)
        message = "the main checkout could not be detached, so nothing moved: %s" % exc
        raise LandingRefusedError(message) from exc
    try:
        _create(root, path, branch, seed)
    except LandingRefusedError:
        _give_back([root, *subs], branch)
        raise
    done = spike.git(root, "switch", "--quiet", "--no-track", "-c", cut, "refs/heads/%s" % branch)
    if done.returncode != 0:
        # The landing tree and its record exist and hold `branch`, so the main checkout cannot switch back until they are gone: undo both, then give the branch back, so a rerun starts from the first-switch shape instead of taking the reuse branch over a detached main checkout.
        _undo_landing(root, path, branch)
        stuck = _give_back([root, *subs], branch)
        message = (
            "the development branch %s could not be cut here, so the landing tree %s was removed%s: %s"
            % (
                cut,
                path,
                (" and %s stays detached" % ", ".join(stuck))
                if stuck
                else " and the branch was given back",
                done.stderr.strip(),
            )
        )
        raise LandingRefusedError(message)
    for sub in subs:
        made = spike.git(sub, "switch", "--quiet", "--no-track", "-c", cut)
        if made.returncode != 0:
            message = (
                "the submodule tree %s could not cut %s at its HEAD (run `git -C %s switch "
                "--no-track -c %s` there once the cause is fixed): %s"
                % (sub, cut, sub, cut, made.stderr.strip())
            )
            raise LandingRefusedError(message)
    log.info(
        "landing tree %s holds %s; the main checkout holds %s, stacked on it" % (path, branch, cut)
    )


def make_landing(root, *, gh=run_gh, seed=None, next_name=None, today=None):
    """Make or reuse the landing tree and return its absolute path. Raises `LandingRefusedError`."""
    try:
        root = lease._main_checkout(root)
    except lease.LeaseRefusedError as exc:
        raise LandingRefusedError(str(exc)) from exc
    path = landing_path(root)
    exists = _guard_path(root, path)
    if exists:
        # Read before the PR lookup: after the merge no PR is open, and the refusal names promote rather than the missing PR.
        _refuse_on_main(path)
    branch = choose_branch(root, gh)
    if exists:
        _reuse(path, branch)
    elif spike.out(root, "symbolic-ref", "-q", "--short", "HEAD") == branch:
        _switch_over(root, path, branch, seed or lease._run_seed, next_name, today)
    else:
        _create(root, path, branch, seed or lease._run_seed)
    return str(path)


def cmd_status(root):
    """Print the landing tree in one line, `<path> on <branch>`, `(no landing record)`, or `(landing record unreadable: <defect>)`; always rc 0. The commands' Branch lines call this instead of reading the record with grep, so their allowed-tools name one exact command."""
    policy = _policy()
    record, defect = policy.read_landing_record(str(root))
    if record is None:
        sys.stdout.write(
            "(landing record unreadable: %s)\n" % defect if defect else "(no landing record)\n"
        )
        return 0
    branch = (
        subprocess.run(
            ["git", "-C", record["path"], "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or "(detached)"
    )
    sys.stdout.write("%s on %s\n" % (record["path"], branch))
    return 0


def cmd_landing(args):
    if args[:1] == ["--promote"]:
        return landing_promote.cmd_promote(args[1:])
    if args == ["--status"]:
        return cmd_status(paths.repo_root())
    if args:
        log.error("Unknown option: %s" % args[0])
        return 1
    try:
        path = make_landing(paths.repo_root())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        log.error("refused: %s" % exc)
        return 1
    sys.stdout.write(path + "\n")
    sys.stdout.flush()
    return 0
