"""Refuse a rebase, a pull or a merge while the repository it runs in holds tracked uncommitted work that is not the hook's own session state.

WHY. This checkout is shared by several live sessions and their work stays uncommitted until its owner commits it. A rebase or merge that starts over a modified tracked file either stops on it, or carries it through a history rewrite and a conflict resolution nobody who owns it is watching; `git merge --abort` says in its own manual that it cannot always reconstruct the pre-merge changes. The one party who can make the tree safe to rebase is the owner, by committing.

WHY A HOOK AND NOT THE SKILL'S PROSE. Operator ruling 2026-10-09 made /branch-rebase AI-invocable and said where something is not covered, a guard covers it instead of the skill's prose. Step 0 of .claude/commands/branch-rebase.md already says "working tree clean, and if it is not, report whose work it is and stop". A read-only audit of 100 spellings through the live pre-bash chain found nothing enforcing it: `git rebase origin/main`, `git pull --rebase`, `git merge origin/main` and `git -C private/renet rebase origin/main` all answered rc 0 on a dirty tree. git's own refusal names paths but not owners, and the next move a session reaches for after it is `--autostash` or `git stash`, which block_destructive_git_restore refuses as the discard they are.

THE RULE, deliberately the simple one the audit proposed: any modified tracked path refuses, in the console or in the submodule the command runs in, except the paths the stop hook and the worklist verbs rewrite on their own schedule. Those are `.claude/hooks/stop/wl_git.py`'s definition (`is_session_state`: `agent/<session>/STATE.md`, `agent/ledgers/*.jsonl`, `agent/worklist/*.jsonl`, `agent/plans/QUEUE.md`, `agent/reviews/**`, `agent/reggate/**`, `.claude/settings.local.json`), read from there rather than copied.

WHICH PATHS ARE DIRTY IS wl_git's ANSWER TOO (`dirty_paths`), not a second probe. It reads the work tree with submodules ignored and the index with them INCLUDED, because a STAGED gitlink passes git's up-front check and then stops the rebase partway with `.git/rebase-merge` left behind (measured on git 2.53.0, recorded on that function). This guard's own `git status --ignore-submodules=all` dropped exactly that case (worklist #dbbed0b6). Untracked files and a submodule whose work tree merely moved are not counted, because git does not count them either.

THE EXEMPTION IS NOT A PROMISE. git itself refuses a rebase while ANY tracked file is modified, volatile session state included, so a tree whose only dirt is a STATE.md passes this guard and is still stopped by git. `.claude/hooks/stop/worklist.py --git rebase-preflight <me>` is the verb that names whose document is in the way; the refusal points there.

`git rebase --skip` IS REFUSED in this checkout on any tree, clean or not: it DROPS the commit being replayed, and /branch-rebase forbids it (its conflict steps). The refusal points to `git rebase --abort`, which returns to the pre-rebase tip.

NOT REFUSED: `--continue`, `--abort`, `--quit` (they finish or undo a rebase already started), `git merge --ff-only` and `git pull --ff-only` (a fast-forward cannot conflict, and git refuses it on its own when a modified file is in the way; pr-merge step 7 runs `git pull --ff-only` on `main`), and any repository outside this checkout.

FAIL CLOSED: a status probe that fails, a command that moves git's idea of the work tree (`--git-dir`, `--work-tree`, `GIT_DIR=`, `GIT_WORK_TREE=` on the command line), and a project directory that cannot be named (`CLAUDE_PROJECT_DIR` unset and the hook outside every checkout) are refused, because the tree the guard would read is not known to be the tree the rebase would touch. Every other command is still allowed then: only a rebase, pull or merge that would start is judged.
"""

import functools
import importlib
import os
import subprocess

from rediacc_hooks import commit_policy, hookio, shellscan, syspath

CHAIN = "pre-bash"
ORDER = 60

# The exemption decides everything this guard allows on a dirty tree. Planting `True` there exempts every path, so a peer's modified file stops refusing the rebase that would carry it.
DEFECT = (
    "    return _wl_git().is_session_state(path)\n",
    "    return True\n",
)

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


def _fixture_git(cwd, *args):
    """`git` for the fixture builders, with the ambient config shut out."""
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": "/nonexistent",
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    )


# Every path the worlds below commit, so each world differs from the others only in what it then modifies.
_SEEDED = (
    "src/app.ts",
    "agent/d00dfeed/STATE.md",
    "agent/ledgers/judge.jsonl",
    "agent/worklist/d00dfeed.jsonl",
    "agent/plans/QUEUE.md",
    "agent/reviews/0831-1/clean.jsonl",
    "agent/reggate/0831-1.jsonl",
    "agent/plans/PLAN-x.md",
)


def _seeded(path):
    path.mkdir(parents=True)
    _fixture_git(path, "init", "-q", "--initial-branch=main")
    for rel in _SEEDED:
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text("v1\n", encoding="utf-8")
    _fixture_git(path, "add", "-A")
    _fixture_git(path, "commit", "-qm", "seed")
    _fixture_git(path, "checkout", "-q", "-b", "0831-1")
    return path


def _clean(path):
    """Nothing modified, one untracked file: untracked work is not what a rebase touches."""
    _seeded(path)
    (path / "notes.txt").write_text("untracked\n", encoding="utf-8")
    return path


def _volatile(path):
    """Only the hook's own session state is modified: allowed here, though git itself still refuses."""
    _seeded(path)
    for rel in _SEEDED:
        if rel.startswith("agent/") and rel != "agent/plans/PLAN-x.md":
            (path / rel).write_text("v2\n", encoding="utf-8")
    return path


def _dirty(path):
    """A peer's modified source file and a modified plan beside the volatile state: the two real paths are named, the volatile ones are not."""
    _volatile(path)
    (path / "src/app.ts").write_text("peer edit\n", encoding="utf-8")
    (path / "agent/plans/PLAN-x.md").write_text("v2\n", encoding="utf-8")
    return path


def _staged(path):
    """Staged and not committed is uncommitted too: `git rebase` refuses a dirty index as well."""
    _seeded(path)
    (path / "src/app.ts").write_text("staged\n", encoding="utf-8")
    _fixture_git(path, "add", "src/app.ts")
    return path


def _gitlink(path):
    """Only a STAGED submodule pointer moved: git's up-front check passes it and the rebase then stops partway, so it refuses (worklist #dbbed0b6). `--ignore-submodules=all` hid it from the old probe."""
    _seeded(path)
    _fixture_git(path, "update-index", "--add", "--cacheinfo", "160000,%s,private/sub" % ("1" * 40))
    _fixture_git(path, "commit", "-qm", "pin a submodule")
    _fixture_git(path, "update-index", "--cacheinfo", "160000,%s,private/sub" % ("2" * 40))
    return path


FIXTURES = {
    "rebase-clean": _clean,
    "rebase-volatile": _volatile,
    "rebase-dirty": _dirty,
    "rebase-staged": _staged,
    "rebase-gitlink": _gitlink,
}

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (name, {"CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name}, {}) for name in sorted(FIXTURES)
]

EDGE_CASES = [
    # Refused in `rebase-dirty`, `rebase-staged` and `rebase-gitlink`, allowed in `rebase-clean` and `rebase-volatile`: the worlds are the two directions.
    ("a rebase onto origin/main", "git rebase origin/main"),
    ("an interactive rebase", "git rebase -i origin/main"),
    ("a rebase with --onto", "git rebase --onto origin/main HEAD~3"),
    ("a rebase with no upstream named", "git rebase"),
    ("a pull --rebase", "git pull --rebase"),
    ("a pull -r", "git pull -r origin main"),
    ("a plain pull merges", "git pull"),
    ("a merge of a ref", "git merge origin/main"),
    ("a fetch then a rebase", "git fetch origin && git rebase origin/main"),
    ("a rebase behind a cd into the tree", "cd . && git rebase origin/main"),
    ("a rebase under -C .", "git -C . rebase origin/main"),
    ("a rebase in a wrapper payload", "sh -c 'git rebase origin/main'"),
    # Never refused: continuing or undoing, a fast-forward, prose, and other commands.
    ("control: --continue", "git rebase --continue"),
    ("control: --abort", "git rebase --abort"),
    # Refused in every world, clean included: `--skip` drops the commit being replayed (worklist #dbbed0b6).
    ("refused: --skip drops the replayed commit", "git rebase --skip"),
    ("refused: --skip by unique prefix", "git rebase --sk"),
    ("refused: --skip behind a wrapper", "sh -c 'git rebase --skip'"),
    ("control: --skip outside this checkout", "git -C /tmp rebase --skip"),
    ("control: --quit", "git rebase --quit"),
    ("control: merge --abort", "git merge --abort"),
    ("control: merge --continue", "git merge --continue"),
    ("control: merge --ff-only", "git merge --ff-only origin/main"),
    ("control: pull --ff-only", "git pull --ff-only"),
    ("control: prose about a rebase", "echo 'git rebase origin/main later'"),
    ("control: a quoted commit message", 'git commit -m "rebase onto main" -- x'),
    ("control: a fetch", "git fetch origin --prune"),
    ("control: a rebase outside this checkout", "git -C /tmp rebase origin/main"),
    # Fail closed in every world: a tree the guard cannot read.
    ("blind: --work-tree moves the tree", "git --work-tree=. rebase origin/main"),
    ("blind: GIT_DIR on the command line", "GIT_DIR=.git git rebase origin/main"),
    ("blind: --git-dir", "git --git-dir=.git merge origin/main"),
]


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
        repo = commit_policy.scoped_repo(run, base, root, created)
        if repo and not commit_policy.is_inside(repo, root) and not why:
            continue
        repo = repo or root
        same = os.path.realpath(repo) == os.path.realpath(root)
        where = "this checkout" if same else os.path.relpath(repo, root)
        if skip:
            return SKIP, {"verb": verb, "where": where}
        paths = dirty_paths(repo)
        if paths is None:
            return BLIND, {"verb": verb, "why": "`git status` failed in %s" % where}
        real = [p for p in paths if not exempt(p)]
        if not real:
            continue
        listed = ["  %s" % p for p in real[:SHOWN]]
        if len(real) > SHOWN:
            listed.append("  ... and %d more" % (len(real) - SHOWN))
        return MESSAGE, {"verb": verb, "where": where, "paths": "\n".join(listed)}
    return None


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW
    # An unnamed root is not a pass (review 72e7ac97.1): `refusal` refuses a starting rebase, pull or merge as BLIND then, and lets every other command through.
    root = shellscan.repo_root_env()
    base = ev.field("cwd") or root
    found = refusal(cmd, root, base)
    if found is None:
        return hookio.ALLOW
    template, fields = found
    ev.warn(template % fields)
    return hookio.DENY
