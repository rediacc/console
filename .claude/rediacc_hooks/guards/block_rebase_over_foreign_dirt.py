"""Refuse a rebase, a pull or a merge while the repository it runs in holds tracked uncommitted work that is not the hook's own session state.

WHY. This checkout is shared by several live sessions and their work stays uncommitted until its owner commits it. A rebase or merge that starts over a modified tracked file either stops on it, or carries it through a history rewrite and a conflict resolution nobody who owns it is watching; `git merge --abort` says in its own manual that it cannot always reconstruct the pre-merge changes. The one party who can make the tree safe to rebase is the owner, by committing.

WHY A HOOK AND NOT THE SKILL'S PROSE. Operator ruling 2026-10-09 made /branch-rebase AI-invocable and said where something is not covered, a guard covers it instead of the skill's prose. Step 0 of .claude/commands/branch-rebase.md already says "working tree clean, and if it is not, report whose work it is and stop". A read-only audit of 100 spellings through the live pre-bash chain found nothing enforcing it: `git rebase origin/main`, `git pull --rebase`, `git merge origin/main` and `git -C private/renet rebase origin/main` all answered rc 0 on a dirty tree. git's own refusal names paths but not owners, and the next move a session reaches for after it is `--autostash` or `git stash`, which block_destructive_git_restore refuses as the discard they are.

THE RULE, deliberately the simple one the audit proposed: any modified tracked path refuses, in the console or in the submodule the command runs in, except the paths the stop hook and the worklist verbs rewrite on their own schedule. Those are `.claude/hooks/stop/wl_git.py`'s definition (`is_session_state`: `agent/<session>/STATE.md`, `agent/ledgers/*.jsonl`, `agent/worklist/*.jsonl`, `agent/plans/QUEUE.md`, `agent/reviews/**`, `agent/reggate/**`, `.claude/settings.local.json`), read from there rather than copied.

WHICH PATHS ARE DIRTY IS wl_git's ANSWER TOO (`dirty_paths`), not a second probe. It reads the work tree with submodules ignored and the index with them INCLUDED, because a STAGED gitlink passes git's up-front check and then stops the rebase partway with `.git/rebase-merge` left behind (measured on git 2.53.0, recorded on that function). This guard's own `git status --ignore-submodules=all` dropped exactly that case (worklist #dbbed0b6). Untracked files and a submodule whose work tree merely moved are not counted, because git does not count them either.

THE EXEMPTION IS NOT A PROMISE. git itself refuses a rebase while ANY tracked file is modified, volatile session state included, so a tree whose only dirt is a STATE.md passes this guard and is still stopped by git. `.claude/hooks/stop/worklist.py --git rebase-preflight <me>` is the verb that names whose document is in the way; the refusal points there.

`git rebase --skip` IS REFUSED in this checkout on any tree, clean or not: it DROPS the commit being replayed, and /branch-rebase forbids it (its conflict steps). The refusal points to `git rebase --abort`, which returns to the pre-rebase tip.

NOT REFUSED: `--continue`, `--abort`, `--quit` (they finish or undo a rebase already started), `git merge --ff-only` and `git pull --ff-only` (a fast-forward cannot conflict, and git refuses it on its own when a modified file is in the way; pr-merge step 7 runs `git pull --ff-only` on `main`), and any repository outside this checkout, `--skip` included, whenever this checkout can be named.

A REBASE OF THE MAIN CHECKOUT ONTO A BASE WITHOUT THE HOOK STAND-DOWN IS REFUSED, on a clean tree too (box R20261123.3 of agent/plans/PLAN-stop-hook-retro-20261123.md, decision D3). Every hook is read from `$CLAUDE_PROJECT_DIR/.claude/...`, the main checkout's working tree, and while a rebase is halted there that tree is `<onto>` plus the steps replayed so far. The stand-down that keeps the hooks from writing tracked records mid-operation (`wl_git.operation_in_progress`, worklist #b07162cf) is therefore absent until its own step replays whenever `<onto>` lacks it: on 2026-11-23 a 273-step rebase halted at step 26, the old hooks dirtied the tree, `git rebase --continue` refused with git's merge-conflict message, and 44 minutes went before the rebase was redone in the landing tree. The probe reads `git show <onto>:.claude/hooks/stop/wl_git.py` for `def operation_in_progress` (STANDDOWN_PROBE), so the refusal expires by itself once the base carries the function, and reopens only if a future stand-down moves the probe. The onto is `--onto`, else the upstream operand, else `@{upstream}`; under `--keep-base` it is the merge-base git replays onto. An onto git cannot resolve is allowed (git refuses that rebase itself and changes nothing), and an onto the walk cannot read (`"origin/${BASE:-main}"`, a command substitution) is judged against `origin/main`, the base the refusal expires against. A linked tree (the landing tree, a lease, an operator's worktree) is never probed: its hooks are not the ones the main checkout's sessions run, which is why the landing tree is the route the refusal names.

FAIL CLOSED: a status probe that fails, a command that moves git's idea of the work tree (`--git-dir`, `--work-tree`, `GIT_DIR=`, `GIT_WORK_TREE=` on the command line), and a project directory that cannot be named (`CLAUDE_PROJECT_DIR` unset and the hook outside every checkout) are refused, because the tree the guard would read is not known to be the tree the rebase would touch. With no project directory, "outside this checkout" cannot be decided either (`git -C /tmp ...` and `git -C <the checkout> ...` look alike to a guard that does not know where the checkout is), so then EVERY rebase, pull or merge that would start, and every `git rebase --skip`, is refused wherever it points (review 30573c81.4). Every other command is still allowed.
"""

import functools
import importlib
import os

from rediacc_hooks import commit_policy, hookio, shellscan, syspath
from rediacc_hooks.guards import tables

__getattr__ = tables(
    "block_rebase_over_foreign_dirt",
    "EDGE_CASES",
    "ENVS",
    "FIXTURES",
    "_SEEDED",
    "_clean",
    "_dirty",
    "_fixture_git",
    "_gitlink",
    "_seeded",
    "_staged",
    "_volatile",
)

CHAIN = "pre-bash"
ORDER = 59

# The exemption decides everything this guard allows on a dirty tree. Planting `True` there exempts every path, so a peer's modified file stops refusing the rebase that would carry it.
DEFECT = (
    "    return _wl_git().is_session_state(path)\n",
    "    return True\n",
)
# Planted, the bound trees are the session root alone, so a rebase, pull or merge typed in the sibling bound tree goes unjudged again (box LT11).
TWO_TREE_DEFECT = ("trees = commit_policy.bound_trees(root)", "trees = [root]")
# Each planted, the stand-down probe stops refusing: `carried` answers the base carries the stand-down whatever it holds, `main` reads every tree as linked, so a rebase of the main checkout onto a base without it goes through (box R20261123.3).
MUTANTS = {
    "standdown-carried": (
        '    return STANDDOWN_PROBE[1] in (text or "")\n',
        "    return True\n",
    ),
    "standdown-main": (
        "    return bool(main) and os.path.realpath(main) == top\n",
        "    return False\n",
    ),
}

# The file and the definition a base must carry for its hooks to stand down mid-rebase (worklist #b07162cf). The refusal ends by itself once the onto base holds them.
STANDDOWN_PROBE = (".claude/hooks/stop/wl_git.py", "def operation_in_progress")
# The base an onto the walk cannot read is judged against: the one whose stand-down ends the refusal.
STANDDOWN_DEFAULT_ONTO = "origin/main"

# The subcommand flags that continue or undo an integration already in progress, and so start nothing. `skip` is among them, and is refused on its own (SKIP) because what it finishes it finishes by dropping a commit.
REBASE_CONTROL = ("continue", "abort", "skip", "quit", "edit-todo", "show-current-patch")
MERGE_CONTROL = ("continue", "abort", "quit")
PULL_CONTROL_WORDS = frozenset(("--ff-only",))
PULL_REBASE_WORDS = ("--rebase", "-r")

# Global options and command-line variables that point git at another work tree or repository than the one the walk resolves.
TREE_OPTIONS = ("--git-dir", "--work-tree")
TREE_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")

# How many dirty paths the refusal lists before summarising the rest.
SHOWN = 12

MESSAGE = (
    "BLOCKED: `%(verb)s` would start over uncommitted tracked work in %(where)s:\n"
    "%(paths)s\n"
    "\n"
    "This checkout is shared by several live sessions, and uncommitted work here may be a "
    "peer's. A rebase or merge over it either stops on it or carries it through a history "
    "rewrite and a conflict resolution its owner is not watching. The work is committed BY "
    "ITS OWNER first; it is never stashed, autostashed, restored or checked out to make the "
    "tree clean (block_destructive_git_restore refuses each of those), and never committed by "
    "a session that did not write it. `git status --short` and `.claude/hooks/stop/worklist.py "
    "--list --open` show what is dirty and which sessions are live.\n"
    "\n"
    "Session state the stop hook rewrites (agent/<session>/STATE.md, agent/ledgers/*.jsonl, "
    "agent/worklist/*.jsonl, agent/plans/QUEUE.md, agent/reviews/**, agent/reggate/**) and "
    ".claude/settings.local.json are not counted here, but git itself still refuses a rebase "
    "while ANY tracked file is modified: `.claude/hooks/stop/worklist.py --git rebase-preflight "
    "<me>` names whose document is in the way.\n"
    "\n"
    "Operator ruling 2026-10-09: /branch-rebase is AI-invocable, and what its prose forbids "
    "(step 0: report whose work it is and stop) a guard refuses. The hook is the guarantee."
)

SKIP = (
    "BLOCKED: `%(verb)s` would DROP the commit being replayed in %(where)s. `--skip` discards "
    "that commit's changes outright, and nothing afterwards says it is gone; /branch-rebase "
    "forbids it for that reason.\n"
    "\n"
    "To leave a rebase that cannot be finished, run `git rebase --abort`: it returns the branch "
    "to its pre-rebase tip. To finish it, resolve the conflict and run `git rebase --continue`. "
    "If the replayed commit is genuinely empty after resolution (its change already in the "
    "base), say so to the operator; dropping it is theirs to run with `!`.\n"
    "\n"
    "Operator ruling 2026-10-09: /branch-rebase is AI-invocable, and what its prose forbids a "
    "guard refuses."
)

STANDDOWN = (
    "BLOCKED: `%(verb)s` would rebase the main checkout onto %(onto)s (%(sha)s), whose "
    "%(probe)s has no `%(needle)s`.\n"
    "\n"
    "Every hook runs from the main checkout's working tree, and while a rebase is halted there "
    "that tree is the onto base plus the steps replayed so far. This base predates the hook "
    "stand-down (worklist #b07162cf), so at a halted step the Stop hook, the per-commit reviewer "
    "and the ledgers write tracked files again, and `git rebase --continue` then refuses with "
    "git's merge-conflict message while `git ls-files -u` is empty. On 2026-11-23 that halted a "
    "273-step rebase at step 26 and cost 44 minutes.\n"
    "\n"
    "Run the rebase where the hooks are not read from, the route that worked:\n"
    "  1. In the landing tree while it is idle on main (`./run.sh worktree landing` prints its "
    "path), detached at the development tip: rebase there onto the same base.\n"
    "  2. Then from the main checkout, with its tree clean, move the development branch to the "
    "rebased tip: `git switch -q --detach <rebased tip>`, `git branch -f <dev branch> <rebased "
    "tip>`, `git switch -q <dev branch>` (git refuses `branch -f` on the branch a tree has "
    "checked out).\n"
    "  3. Never run `git submodule update --init` in the landing tree: it rewrote the main "
    "checkout's `private/account` gitdir pointer (hint 2026-11-23T00:41:52Z).\n"
    "A lease tree is no route: block_lease_boundary refuses every rebase in one.\n"
    "\n"
    "This refusal ends by itself once the onto base carries `%(needle)s` in %(probe)s "
    "(origin/main, once the branch carrying the stand-down merges). Box R20261123.3 of "
    "agent/plans/PLAN-stop-hook-retro-20261123.md; .claude/commands/branch-rebase.md step 3."
)

# The `why` of a BLIND refusal when the project directory itself cannot be named.
NO_ROOT = (
    "the shared checkout is unknown (`CLAUDE_PROJECT_DIR` is unset and the hook does not run "
    "inside a git checkout), so the tree this would touch cannot be read"
)

BLIND = (
    "BLOCKED: `%(verb)s` cannot be judged: %(why)s. This guard refuses a rebase, pull or merge "
    "over uncommitted tracked work in the shared checkout, and a tree it cannot read is not a "
    "clean one. Run it without the override, from the repository itself, so the tree read is "
    "the tree the rebase touches.\n"
    "\n"
    "Operator ruling 2026-10-09: /branch-rebase is AI-invocable, and what its prose forbids a "
    "guard refuses."
)


@functools.cache
def _wl_git():
    """wl_git.py, the one definition of what is dirty and what is session state, loaded once and only for a rebase, pull or merge (never for other commands); importlib keeps it lazy without a late import statement or a module global."""
    syspath.on_sys_path(syspath.STOP_DIR)
    return importlib.import_module("wl_git")


def exempt(path):
    """Whether a modified tracked path is the hook's own churn rather than somebody's work. `is_session_state` already covers `.claude/settings.local.json` (worklist #dbbed0b6)."""
    return _wl_git().is_session_state(path)


def starts_integration(sub, args):
    """Whether `git <sub> <args>` starts a rebase or merge, as opposed to continuing, undoing or fast-forwarding one."""
    if sub == "rebase":
        parsed = shellscan.git_args("rebase", args)
        return not any(parsed.on(name) for name in REBASE_CONTROL)
    if sub == "merge":
        parsed = shellscan.git_args("merge", args)
        return not any(parsed.on(name) for name in (*MERGE_CONTROL, "ff-only"))
    if sub == "pull":
        head = args[: args.index("--")] if "--" in args else args
        words = [a.split("=", 1)[0] for a in head]
        rebasing = any(w in PULL_REBASE_WORDS for w in words)
        return rebasing or not any(w in PULL_CONTROL_WORDS for w in words)
    return False


def dirty_paths(repo):
    """The tracked paths `git rebase` would refuse or stop on in `repo`, staged gitlinks included; None when the probe itself fails. wl_git's answer, so the guard and `--git rebase-preflight` never disagree."""
    return _wl_git().dirty_paths(repo)


def rebase_onto(args):
    """`(onto, keep_base_upstream)` for the words after `git rebase`: the base it would replay onto (`--onto`, else the upstream operand, else `@{upstream}`), and, under `--keep-base`, the upstream whose merge-base with HEAD is the real base. `(None, None)` for `--root` with no `--onto`, which replays onto nothing."""
    parsed = shellscan.git_args("rebase", args)
    upstream = parsed.operands[0] if parsed.operands else None
    onto = parsed.last("onto")
    if parsed.on("keep-base"):
        return None, upstream or "@{upstream}"
    if onto is not None:
        return onto, None
    if upstream is not None:
        return upstream, None
    if parsed.on("root"):
        return None, None
    return "@{upstream}", None


def is_main_checkout(repo):
    """Whether `repo` sits at the top of its repository's MAIN checkout (the tree holding the common `.git`), the tree whose `.claude/` every hook is read from. A linked tree and a submodule answer False."""
    top = os.path.realpath(commit_policy.toplevel(repo) or repo)
    main = commit_policy.main_checkout(repo)
    return bool(main) and os.path.realpath(main) == top


def carries_standdown(text):
    """Whether a base's copy of STANDDOWN_PROBE[0] (`text`, None when the base has no such file) defines the stand-down."""
    return STANDDOWN_PROBE[1] in (text or "")


def standdown_refusal(repo, args, verb):
    """The STANDDOWN fields when `git rebase <args>` in `repo` would replay the main checkout onto a base without the hook stand-down, else None."""
    if not is_main_checkout(repo):
        return None
    onto, keep = rebase_onto(args)
    if onto is None and keep is None:
        return None
    word = onto if onto is not None else keep
    named = word
    if shellscan.unresolved(word):
        word = named = STANDDOWN_DEFAULT_ONTO
    sha = commit_policy.git(
        ["rev-parse", "--verify", "--quiet", "--end-of-options", "%s^{commit}" % word],
        cwd=repo,
        foreign=True,
    )
    if not sha:
        return None
    if keep is not None:
        sha = commit_policy.git(["merge-base", sha, "HEAD"], cwd=repo, foreign=True)
        if not sha:
            return None
        named = "the merge-base of %s and HEAD" % named
    text = commit_policy.git(["show", "%s:%s" % (sha, STANDDOWN_PROBE[0])], cwd=repo, foreign=True)
    if carries_standdown(text):
        return None
    return {
        "verb": verb,
        "onto": named,
        "sha": sha[:10],
        "probe": STANDDOWN_PROBE[0],
        "needle": STANDDOWN_PROBE[1],
    }


def _blind(run, globs):
    """Why the tree this command would touch is not the one the guard reads, or ""."""
    for opt in TREE_OPTIONS:
        if any(g == opt or g.startswith(opt + "=") for g in globs):
            return "`%s` points git at a tree this guard does not read" % opt
    for var in TREE_VARS:
        if var in run.env:
            return "`%s` on the command line points git at a tree this guard does not read" % var
    return ""


def refusal(cmd, root, base):
    """`(template, fields)` for the first walked rebase, pull or merge that would start over foreign dirt, else None."""
    created = None
    trees = None
    for run in commit_policy.git_runs(cmd):
        argv = run.xargv if run.xargv is not None else run.argv
        globs, sub, args = commit_policy.git_split(argv)
        skip = sub == "rebase" and shellscan.git_args("rebase", args).on("skip")
        if not skip and not starts_integration(sub, args):
            continue
        verb = " ".join(["git", sub, *args]).strip()
        if not root:
            return BLIND, {"verb": verb, "why": NO_ROOT}
        why = _blind(run, globs)
        if why and not skip:
            return BLIND, {"verb": verb, "why": why}
        if created is None:
            created = commit_policy.created_dirs(cmd, base)
        if trees is None:
            trees = commit_policy.bound_trees(root)
        repo = commit_policy.scoped_repo(run, base, root, created, trees=trees)
        # Either bound tree is this checkout (box LT11): the landing tree is shared with the landing session the same way.
        if repo and not commit_policy.is_ours(repo, root, trees) and not why:
            continue
        repo = repo or root
        same = os.path.realpath(repo) == os.path.realpath(root)
        where = (
            "this checkout"
            if same
            else os.path.relpath(repo, root)
            if commit_policy.is_inside(repo, root)
            else repo
        )
        if skip:
            return SKIP, {"verb": verb, "where": where}
        paths = dirty_paths(repo)
        if paths is None:
            return BLIND, {"verb": verb, "why": "`git status` failed in %s" % where}
        real = [p for p in paths if not exempt(p)]
        if real:
            listed = ["  %s" % p for p in real[:SHOWN]]
            if len(real) > SHOWN:
                listed.append("  ... and %d more" % (len(real) - SHOWN))
            return MESSAGE, {"verb": verb, "where": where, "paths": "\n".join(listed)}
        # A clean tree still refuses a rebase whose halted steps would run hooks without the stand-down (box R20261123.3).
        stale = standdown_refusal(repo, args, verb) if sub == "rebase" else None
        if stale:
            return STANDDOWN, stale
    return None


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW
    # An unnamed root is not a pass (review 72e7ac97.1): `refusal` refuses a starting rebase, pull or merge, and any `--skip`, as BLIND then, wherever it points, and lets every other command through.
    root = shellscan.repo_root_env(ev)
    base = ev.field("cwd") or root
    found = refusal(cmd, root, base)
    if found is None:
        return hookio.ALLOW
    template, fields = found
    ev.warn(template % fields)
    return hookio.DENY
