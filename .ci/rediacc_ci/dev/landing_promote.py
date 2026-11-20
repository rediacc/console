"""`./run.sh worktree landing --promote`: after the landing PR rebase-merges, the development branch becomes the landing branch (PLAN-two-track-merge-dev LT16).

Order, each step refusing before anything moves where it can:

1. The landing record binds a tree and a branch, the main checkout holds another `MMDD-N` branch (the development branch), and both trees are clean.
2. The landing PR is MERGED (gh answers; anything else is a refusal), and every landing commit has a patch-equivalent on origin/main.
3. The development branch rebases onto origin/main. The landing copies drop as absorbed, and the RB4 proof (`wl_rebase.rebase_proof`) must name no commit missing; a conflict aborts the rebase and a missing commit puts the branch back at its old tip.
4. The main checkout detaches, the landing tree switches to the development branch, and the record is rewritten to bind it.
5. The next `MMDD-N` is cut from origin/main in the main checkout, and `gh pr ready <draft>` is printed.

Only the printed `gh pr ready` line is data on stdout; everything else goes to stderr. Submodule trees are not moved.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.dev import worktree_lease as lease
from rediacc_ci.dev import worktree_spike as spike

REMOTE = "origin"
BASE = "main"
UPSTREAM = "%s/%s" % (REMOTE, BASE)
GH_TIMEOUT = 60
SHOWN = 3

PROMOTE_HELP = """\
Usage: ./run.sh worktree landing --promote

After the landing PR merged: rebase the development branch onto origin/main
(the landing commits drop as absorbed), move it into the landing tree, rewrite
the landing record, cut the next MMDD-N from origin/main in the main checkout,
and print `gh pr ready <draft>`. Refused: a dirty tree in either checkout, a
landing PR that is not MERGED, a landing commit missing from origin/main, a
rebase conflict, and a rebase that loses a development commit.
"""


class PromoteRefusedError(RuntimeError):
    """Promotion did not run to the end, and the message says what moved."""


def run_gh(args, cwd):
    """`(rc, stdout)` of `gh <args>`; 127 when gh cannot run."""
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


def _gh_json(gh, args, cwd):
    """The parsed object gh printed, or None when gh failed or printed no object."""
    rc, text = gh(args, cwd)
    if rc != 0:
        return None
    try:
        data = json.loads(text or "")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _today():
    """The local `MMDD`, the clock block_second_branch names branches by."""
    return datetime.datetime.now().astimezone().strftime("%m%d")


def _default_next_name(root, today):
    return spike.load_commit_policy().next_branch_name(str(root), today, gh=True)


def _dirty(tree):
    text = spike.must(tree, "status", "--porcelain", "--untracked-files=all")
    return [line for line in text.splitlines() if line]


def _must(tree, *args):
    try:
        return spike.must(tree, *args)
    except RuntimeError as exc:
        raise PromoteRefusedError(str(exc)) from exc


def _premises(main, gh):
    """`(landing path, landing branch, development branch)`, refusing before anything moves."""
    policy = spike.load_commit_policy()
    record, problem = policy.read_landing_record(str(main))
    if record is None:
        message = "no landing tree to promote into: %s" % (
            problem or "%s names none" % policy.LANDING_RECORD_NAME
        )
        raise PromoteRefusedError(message)
    landing, landing_branch = pathlib.Path(record["path"]), record["branch"]
    dev = spike.out(main, "symbolic-ref", "-q", "--short", "HEAD")
    if not policy.BRANCH_SHAPE.match(dev) or dev == landing_branch:
        message = "the main checkout %s holds no development branch (HEAD %s)" % (
            main,
            dev or "detached",
        )
        raise PromoteRefusedError(message)
    for tree in (main, landing):
        rows = _dirty(tree)
        if rows:
            message = "%s is dirty: %s" % (tree, " | ".join(rows[:SHOWN]))
            raise PromoteRefusedError(message)
    state = _gh_json(gh, ["pr", "view", landing_branch, "--json", "state"], main)
    if state is None:
        message = "gh could not say the state of the landing PR on %s" % landing_branch
        raise PromoteRefusedError(message)
    if state.get("state") != "MERGED":
        message = "the landing PR on %s is %s, not MERGED" % (landing_branch, state.get("state"))
        raise PromoteRefusedError(message)
    return landing, landing_branch, dev


def _fetch_and_check(main, landing_branch):
    """Fetch origin/main and refuse when a landing commit has no patch-equivalent there."""
    _must(
        main,
        "fetch",
        "--quiet",
        "--no-tags",
        REMOTE,
        "+refs/heads/%s:refs/remotes/%s" % (BASE, UPSTREAM),
    )
    marks = _must(main, "cherry", UPSTREAM, "refs/heads/%s" % landing_branch).splitlines()
    left = [line.split()[1] for line in marks if line.startswith("+ ")]
    if left:
        message = "%d landing commit(s) have no copy on %s, so the merge is not complete: %s" % (
            len(left),
            UPSTREAM,
            ", ".join(sha[:12] for sha in left[:SHOWN]),
        )
        raise PromoteRefusedError(message)


def _rebase(main, dev):
    """Rebase `dev` (checked out in `main`) onto origin/main and return `(old tip, proof)`."""
    old = _must(main, "rev-parse", "--verify", "refs/heads/%s^{commit}" % dev)
    done = spike.git(main, "-c", "rebase.autoStash=false", "rebase", "--quiet", UPSTREAM)
    if done.returncode != 0:
        spike.git(main, "rebase", "--abort")
        first = ((done.stderr or done.stdout).strip().splitlines() or ["no output"])[0]
        message = "rebasing %s onto %s stopped, so it was aborted: %s" % (dev, UPSTREAM, first)
        raise PromoteRefusedError(message)
    new = _must(main, "rev-parse", "HEAD")
    proof = lease._hook_module("wl_rebase").rebase_proof(str(main), UPSTREAM, old, new, set())
    if proof is None or proof["missing"]:
        spike.git(main, "reset", "--quiet", "--keep", old)
        lost = (
            ", ".join(s[:12] for s in (proof or {}).get("missing", [])) or "git could not compare"
        )
        message = "the rebase of %s lost development commits (%s), so %s is back at %s" % (
            dev,
            lost,
            dev,
            old[:12],
        )
        raise PromoteRefusedError(message)
    return old, proof


def promote(root, *, gh=run_gh, today=None, next_name=None):
    """Run the promotion and return the `gh pr ready` line. Raises `PromoteRefusedError`."""
    try:
        main = lease._main_checkout(root)
    except lease.LeaseRefusedError as exc:
        raise PromoteRefusedError(str(exc)) from exc
    landing, landing_branch, dev = _premises(main, gh)
    # The name is read before anything moves, so a gh that cannot answer refuses with both trees untouched.
    try:
        cut = (next_name or _default_next_name)(main, today or _today())
    except (OSError, RuntimeError) as exc:
        message = "the next branch name could not be read: %s" % exc
        raise PromoteRefusedError(message) from exc
    _fetch_and_check(main, landing_branch)
    _old, proof = _rebase(main, dev)
    log.info(
        "%s onto %s: %d carried, %d absorbed (the landing copies), %d changed"
        % (dev, UPSTREAM, len(proof["carried"]), len(proof["absorbed"]), len(proof["changed"]))
    )
    _must(main, "switch", "--quiet", "--detach")
    moved = spike.git(landing, "switch", "--quiet", dev)
    if moved.returncode != 0:
        spike.git(main, "switch", "--quiet", dev)
        message = (
            "the landing tree %s could not take %s, so the main checkout holds it again: %s"
            % (
                landing,
                dev,
                moved.stderr.strip(),
            )
        )
        raise PromoteRefusedError(message)
    spike.load_commit_policy().write_landing_record(str(main), str(landing), dev)
    _must(main, "switch", "--quiet", "--no-track", "-c", cut, UPSTREAM)
    log.info("landing tree %s holds %s; the main checkout holds %s" % (landing, dev, cut))
    log.info(
        "%s was rebased: republish it through the guarded lease push before the PR flips ready"
        % dev
    )
    pr = _gh_json(gh, ["pr", "view", dev, "--json", "number,isDraft"], main) or {}
    if pr.get("isDraft") is False:
        log.info("the PR of %s is already ready for review" % dev)
    return "gh pr ready %s" % (pr.get("number") or dev)


def cmd_promote(args):
    if args:
        log.error("Unknown option: %s" % args[0])
        return 1
    try:
        line = promote(paths.repo_root())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        log.error("refused: %s" % exc)
        return 1
    sys.stdout.write(line + "\n")
    sys.stdout.flush()
    return 0
