"""Keep a writer inside its lease tree: commit on the detached HEAD, and nothing that moves the tree or leaves it.

WHY. Operator ruling, ASKED:2026-11-04T10:15Z: "Detached, repo tool" and "Lead cherry-picks". A lease shares its refs with the live checkout, so `git switch main` in one is a real switch (`main` is checked out nowhere while the live branch is), and a push from one needs no second branch to publish a commit nobody spot-checked (agent/plans/PLAN-worktree-lease.md, Design 6).

ACTIVE ONLY IN A LEASE. `commit_policy.lease_root` decides, per command, from that command's own `cd` and `-C`: a linked tree below `<main>/.claude/worktrees/<id>`, or a submodule tree inside one. The same commands from the main checkout, an operator's `.worktrees/<MMDD-N>` or a plain repository are not this guard's business. A pin push from those is the `pre-push` hook's refusal.

REFUSED IN A LEASE:

  git push, switch, cherry-pick, rebase, merge, pull, am, worktree <anything>
  git checkout that moves HEAD (a branch, a commit, `-b`, `--detach`, a name git would turn into a branch); a checkout of paths is left to `block_destructive_git_restore`
  git branch that makes, moves, copies or deletes a branch; update-ref; symbolic-ref with a target
  git commit whose committed paths hold a gitlink or anything under `agent/`
  gh pr <anything>; a `gh api` call that writes

`merge`, `pull`, `am`, `update-ref`, `symbolic-ref` and a branch delete are beyond the plan's list: each is the same act by another verb, and a lease's refs are the live checkout's.

THE GIT-LEVEL TWIN. `pre-commit` and `pre-push` in `.claude/rediacc_hooks/git/` refuse a lease's gitlink and `agent/**` commits and every push, for a subprocess this hook never sees, and refuse a pin push from every repository.

OUT OF REACH, stated: a verb inside an interpreter program or a script. For a commit or a push the git-level twin still answers; the other verbs have no git hook to back them.
"""

import os
import re

from rediacc_hooks import commit_policy, hookio, shellscan
from rediacc_hooks.guards import tables

__getattr__ = tables("block_lease_boundary", "EDGE_CASES", "ENVS", "FIXTURES", "_lease_world")

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 67

# The verdict itself. With it gone every act in a lease goes through.
DEFECT = ("if reason:", "if False:")

MESSAGE = (
    "BLOCKED: %%s\n\nLease tree: %%s\n%s\nOperator ruling ASKED:2026-11-04T10:15Z.\n"
) % commit_policy.LEASE_ADVICE

ALWAYS_REFUSED = frozenset(
    ("push", "switch", "cherry-pick", "rebase", "merge", "pull", "am", "worktree")
)
JUDGED = ALWAYS_REFUSED | {"checkout", "branch", "update-ref", "symbolic-ref", "commit"}
PREFILTER = re.compile(r"\b(?:git|gh)\b")


def _checkout_moves(args, repo, here):
    """Would this `git checkout` move HEAD? Paths do not. A lone name that resolves to neither a commit nor a path is one git may turn into a branch, so it counts."""
    parsed = shellscan.git_checkout_args(args)
    if any(parsed.on(name) or parsed.last(name) for name in ("b", "B", "orphan", "detach")):
        return True
    if parsed.last("pathspec-from-file"):
        return False
    if "--" in args and args[args.index("--") + 1 :]:
        return False
    names = [word for word in parsed.operands if word != "--"]
    if len(names) != 1:
        return False
    if commit_policy.git(["rev-parse", "--verify", "-q", names[0] + "^{commit}"], cwd=repo):
        return True
    return not os.path.lexists(os.path.join(here, names[0]))


def _branch_writes(args):
    if commit_policy._branch_creation(args):
        return True
    parsed = shellscan.git_args("branch", args)
    return parsed.on("delete") or parsed.on("D")


def _commit_reason(run_, cmd, repo, base):
    named = commit_policy.judged_paths(run_, cmd, repo, base)
    staged = commit_policy.diff_changes(repo, "--cached")
    tree = commit_policy.diff_changes(repo, "HEAD")
    if staged is None or tree is None:
        return "UNCHECKED: `git diff` could not be read here, and an unknown is not a pass."
    changed = staged[0] | tree[0]
    offenders = commit_policy.lease_commit_offenders(
        [path for path in named if path in changed], staged[1] | tree[1]
    )
    if offenders:
        return "this commit holds what only the lead commits: %s." % ", ".join(offenders)
    return ""


def _git_reason(run_, cmd, repo, here, base):
    _, sub, args = commit_policy.git_split(run_.argv)
    if sub in ALWAYS_REFUSED:
        return "`git %s` does not run in a lease." % sub
    if sub == "checkout" and _checkout_moves(args, repo, here):
        return "this `git checkout` moves HEAD, and a lease stays on its detached HEAD."
    if sub == "branch" and _branch_writes(args):
        return "this `git branch` writes a branch, and a lease's refs are the live checkout's."
    if sub == "update-ref":
        return "`git update-ref` writes a ref, and a lease's refs are the live checkout's."
    if sub == "symbolic-ref" and len([word for word in args if not word.startswith("-")]) > 1:
        return "this `git symbolic-ref` moves HEAD, and a lease stays on its detached HEAD."
    if sub == "commit":
        return _commit_reason(run_, cmd, repo, base)
    return ""


def _gh_reason(run_):
    parsed = shellscan.gh_args(run_.argv)
    if parsed.on("help"):
        return ""
    if parsed.command[:1] == ("pr",):
        return "`gh pr` does not run in a lease: the one PR is the lead's."
    if parsed.command == ("api",) and shellscan.gh_api_method(parsed) != "GET":
        return "a `gh api` call that writes does not run in a lease."
    return ""


def _judged(run_):
    name = run_.name.rsplit("/", 1)[-1]
    if name == "gh":
        return True
    return name == "git" and run_.git_sub in JUDGED


def _verdict(cmd, base):
    """`(reason, lease)` for the first act of `cmd` that a lease refuses, `("", "")` when there is none."""
    runs = [run_ for run_ in shellscan.every_run(cmd) if _judged(run_)]
    if not runs:
        return "", ""
    created = commit_policy.created_dirs(cmd, base)
    for run_ in runs:
        here = commit_policy.effective_dir(run_, base, created)
        lease = commit_policy.lease_root(here)
        if not lease:
            continue
        if run_.name.rsplit("/", 1)[-1] == "gh":
            reason = _gh_reason(run_)
        else:
            reason = _git_reason(run_, cmd, commit_policy.toplevel(here), here, base)
        if reason:
            return reason, lease
    return "", ""


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "" or not PREFILTER.search(cmd):
        return hookio.ALLOW
    base = ev.field("cwd") or ev.env("CLAUDE_PROJECT_DIR") or os.getcwd()
    reason, lease = _verdict(cmd, base)
    if reason:
        ev.warn_raw(MESSAGE % (reason, lease))
        return hookio.DENY
    return hookio.ALLOW
