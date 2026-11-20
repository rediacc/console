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
from rediacc_ci.dev import worktree_lease as lease
from rediacc_ci.dev import worktree_spike as spike

RECORD_NAME = "rediacc-landing.json"
SUFFIX = "-landing"
REASON = "landing"
GH_TIMEOUT = 60

LANDING_HELP = """\
Usage: ./run.sh worktree landing

Make, or reuse, the landing tree: a sibling of the main checkout named
<checkout>-landing, on the open PR's MMDD-N branch, with each submodule tree on
a branch of the same name and dependencies seeded. Re-running fetches and
fast-forwards it. The last stdout line is the tree's absolute path.

Refused: main, a branch the main checkout holds, another MMDD-N branch checked
out in the main checkout, a second path, and a dirty tree. The main checkout
must be off the PR branch, since git holds one branch in one tree.
"""


class LandingRefusedError(RuntimeError):
    """The landing tree was not made or reused, and the message says why."""


def run_gh(args, cwd):
    """`(rc, stdout)` of `gh <args>`; 127 when gh is absent."""
    try:
        done = subprocess.run(
            ["gh", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            timeout=GH_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return done.returncode, done.stdout


def landing_path(root):
    root = pathlib.Path(root)
    return root.parent / (root.name + SUFFIX)


def record_file(root):
    return pathlib.Path(root) / ".git" / RECORD_NAME


def write_record(root, path, branch):
    """The binding record, schema `{"path": <realpath>, "branch": <MMDD-N>}`. `commit_policy.write_landing_record` supersedes this helper once it lands, and the call switches to it then."""
    target = record_file(root)
    partial = target.with_name("." + target.name + ".partial")
    body = {"path": os.path.realpath(path), "branch": branch}
    partial.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(target)


def read_record(root):
    try:
        data = json.loads(record_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (
        isinstance(data, dict)
        and isinstance(data.get("path"), str)
        and isinstance(data.get("branch"), str)
    ):
        return data
    return None


def _shape():
    return spike.load_commit_policy().BRANCH_SHAPE


def _open_pr_branches(root, gh):
    rc, text = gh(
        ["pr", "list", "--state", "open", "--author", "@me", "--json", "headRefName"], root
    )
    if rc != 0:
        return []
    try:
        rows = json.loads(text or "[]")
    except ValueError:
        return []
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
    if current and current != branch and shape.match(current):
        message = (
            "the main checkout is on the development branch %s while the open PR is on %s: "
            "switch the main checkout to %s, or land %s first" % (current, branch, branch, branch)
        )
        raise LandingRefusedError(message)
    if current == branch:
        message = (
            "the main checkout holds %s and git keeps one branch in one tree: "
            "switch the main checkout to the development branch first" % branch
        )
        raise LandingRefusedError(message)
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
    record = read_record(root)
    if record and os.path.realpath(record["path"]) != os.path.realpath(path):
        message = "the landing tree is bound to %s, so no second path %s" % (record["path"], path)
        raise LandingRefusedError(message)
    if not os.path.lexists(path):
        return False
    if os.path.realpath(path) not in _listed(root):
        message = "%s exists and is not a worktree of this repository" % path
        raise LandingRefusedError(message)
    return True


def _reuse(path, branch):
    held = spike.out(path, "symbolic-ref", "-q", "--short", "HEAD")
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
        if not tree.is_dir() or spike.out(tree, "rev-parse", "HEAD") == sha:
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
    spike.git(root, "fetch", "origin", branch)
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
        spike.must(store, "worktree", "add", *lock, "-b", branch, str(tree), sha)


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
    except (OSError, RuntimeError, subprocess.SubprocessError, spike.InterruptedRunError) as exc:
        _rollback(root, repo, path)
        message = "landing tree not made: %s" % exc
        raise LandingRefusedError(message) from exc


def make_landing(root, *, gh=run_gh, seed=None):
    """Make or reuse the landing tree and return its absolute path. Raises `LandingRefusedError`."""
    try:
        root = lease._main_checkout(root)
    except lease.LeaseRefusedError as exc:
        raise LandingRefusedError(str(exc)) from exc
    path = landing_path(root)
    exists = _guard_path(root, path)
    branch = choose_branch(root, gh)
    if exists:
        _reuse(path, branch)
    else:
        _create(root, path, branch, seed or lease._run_seed)
    return str(path)


def cmd_landing(args):
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
