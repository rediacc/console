"""One live branch per repository, and no agent path to a second one.

WHY. Operator ruling, 2026-09-25: "we should only allow single branch and single PR only. AI agents sometimes decides to open new branches." Before this guard nothing counted branches at all: `block_nonstandard_branch_name` checks a new branch's NAME, so `git checkout -b 0925-1` from `0923-1` went through, and `git push origin HEAD:0925-1` (a new remote branch) was checked by nothing (F2 of the commit-policy plan in agent/plans).

THE INVARIANT (plan section 2). In each repository -- the console, and each submodule under `private/` -- at most one live non-`main` local branch, all carrying the same `MMDD-N` name, and at most one open PR (`block_second_open_pr`) whose head is that branch. A local branch stops being live once its PR is MERGED or CLOSED; `gh pr list --head <b> --state all` answers that, and it is asked only when a creation is being judged, which is rare.

THE SAME ACT IN EVERY FORM, all found by `commit_policy.branch_creations` on the shared lexer (a quoted mention is data; a `sh -c` payload is walked):

  checkout -b/-B, switch -c/-C, branch <new>, branch -c/-C (copy), worktree add -b
  push <remote> <src>:<new>, push -u <remote> <new>
  gh pr create --head <other>, gh api .../git/refs -X POST

A LOCAL creation is allowed only when all of these hold: the checkout is on `main`; no live branch exists; the name is today's `MMDD-(MAX+1)`, MAX taken over consumed PR heads, local and remote-tracking names (the computation `block_nonstandard_branch_name`'s message teaches). In a SUBMODULE the name must instead equal the console's current branch (the coordinated rule `/pr-merge` matches on), and no other live branch may exist there.

A REMOTE name (push, `gh pr create --head`, a `git/refs` POST) is allowed only when it is the repository's current branch. `main` is `block_push_to_protected_branch`'s business, not this guard's.

ALWAYS ALLOWED: a rename (`branch -m <live> <new>`: the count stays at one, and `block_stale_pr_branch_date`'s advice depends on it); every read and delete form; a name that already exists locally (nothing is created); a repository outside this checkout, `/tmp` fixtures included.

`gh` FAILING WHILE A CREATION IS JUDGED IS A REFUSAL, and the message says so and names the operator's `!` route. Liveness that cannot be read is not liveness that was checked.

THE GIT-LEVEL TWIN. `.claude/rediacc_hooks/git/reference-transaction` refuses the same local creations with local facts only (no `gh`), for commands that never reach this hook: the operator's terminal and subprocesses. It honours `COMMIT_POLICY_OK=1`; this guard never does.
"""

import datetime
import os
import subprocess

from rediacc_hooks import commit_policy, hookio

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 46

# The live-count test. With it gone a second branch is cut beside a live one whenever the name happens to be today's next, which is exactly the parallel-branch drift the ruling forbids.
DEFECT = ("if live:", "if False:")

LOCAL_KINDS = frozenset(("checkout-b", "switch-c", "branch", "copy", "worktree"))
REMOTE_KINDS = frozenset(("push", "gh-pr-create", "gh-api-ref"))


def _world(path):
    """A checkout on `main` with a live `0923-1` beside it: the live-count arm's world."""
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_AUTHOR_DATE="2026-01-01T00:00:00+00:00",
        GIT_COMMITTER_DATE="2026-01-01T00:00:00+00:00",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )
    path.mkdir(parents=True)
    for argv in (
        ["init", "-q", "--initial-branch=main"],
        ["commit", "-q", "--allow-empty", "-m", "seed"],
        ["branch", "0923-1"],
    ):
        subprocess.run(["git", *argv], cwd=str(path), check=True, capture_output=True, env=env)
    return path


FIXTURES = {"main-with-live-branch": _world}

# `gh` stubbed to ANSWER with no PRs, so liveness is decided by the local branches alone and the live-count arm is reachable. The default stub fails, which is the refusal arm.
GH_EMPTY = {"gh": "#!/bin/sh\nexit 0\n"}

ENVS = [
    ("main-live", {"CLAUDE_PROJECT_DIR": "{FIXTURE:main-with-live-branch}"}, GH_EMPTY),
    ("main-clean", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, GH_EMPTY),
    ("feature", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, GH_EMPTY),
    ("gh-down", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
]

EDGE_CASES = [
    ("checkout -b beside a live branch", "git checkout -b 0229-1"),
    ("switch -c", "git switch -c 0229-1"),
    ("branch <new>", "git branch 0229-1"),
    ("a push creating a remote branch", "git push origin HEAD:0229-7"),
    ("push -u of a new name", "git push -u origin 0229-7"),
    ("gh pr create with another head", "gh pr create --draft --head 0229-7"),
    ("a wrapper payload", "sh -c 'git checkout -b 0229-1'"),
    ("a name that is not today's next", "git checkout -b 0229-5"),
    ("a rename keeps the count", "git branch -m 0923-1 0229-1"),
    ("a delete", "git branch -d 0923-1"),
    ("a read", "git branch --show-current"),
    ("a scratch repo", "git -C /tmp checkout -b x"),
    ("F1: a grep for the verbs", 'grep -n -e "checkout -b" -e "git branch [a-z0-9]" x.py'),
    ("a heredoc body is data", "cat > n.md <<'EOF'\ngit checkout -b 0229-9\nEOF"),
]


def _refuse(ev, text):
    ev.warn_raw(
        "BLOCKED: %s\n"
        "\n"
        "Operator ruling, 2026-09-25: one branch and one PR per repository, and agents\n"
        "do not open new ones. Work lands on the one live MMDD-N branch; a new branch\n"
        "is cut only from `main`, once the previous one's PR has merged or closed, under\n"
        "today's next name. There is no agent path around this: when a second branch is\n"
        "genuinely wanted, the operator runs it with the `!` prefix.\n" % text
    )
    return hookio.DENY


def _gh_down(ev, exc, name):
    return _refuse(
        ev,
        "`gh` could not answer (%s), so creating `%s` cannot be judged: which branches are "
        "still live, and which names today's merged PRs consumed, both come from it. An "
        "answer that could not be read is not one that was checked."
        % (str(exc).split("\n")[0][:160], name),
    )


def _judge_local(ev, creation, console_top, console_branch, today):
    repo = creation.repo_root
    try:
        live = commit_policy.live_branches(repo, gh=True)
    except commit_policy.GhUnavailableError as exc:
        return _gh_down(ev, exc, creation.name)
    if repo != console_top:
        others = [b for b in live if b != creation.name]
        if creation.name != console_branch or others:
            return _refuse(
                ev,
                "`%s` in the submodule %s. A submodule's branch carries the console's name "
                "(`%s`), and it may hold no other live branch (live: %s)."
                % (
                    creation.name,
                    repo,
                    console_branch or "(detached)",
                    ", ".join(live) or "none",
                ),
            )
        return hookio.ALLOW
    if live:
        return _refuse(
            ev,
            "creating `%s` while `%s` is live. Continue on it: `git switch %s`."
            % (creation.name, live[0], live[0]),
        )
    current = commit_policy.current_branch(repo)
    if current != "main":
        return _refuse(
            ev,
            "creating `%s` from `%s`. A new branch is cut from `main`."
            % (creation.name, current or "(detached)"),
        )
    try:
        want = commit_policy.next_branch_name(repo, today, gh=True)
    except commit_policy.GhUnavailableError as exc:
        return _gh_down(ev, exc, creation.name)
    if creation.name != want:
        return _refuse(
            ev, "`%s` is not today's next branch name; that is `%s`." % (creation.name, want)
        )
    return hookio.ALLOW


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW
    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    base = ev.field("cwd") or root
    creations = [
        c
        for c in commit_policy.branch_creations(cmd, root, base)
        if c.kind in LOCAL_KINDS or c.kind in REMOTE_KINDS
    ]
    if not creations:
        return hookio.ALLOW
    console_top = commit_policy.toplevel(root)
    console_branch = commit_policy.current_branch(console_top) if console_top else ""
    # LOCAL time, deliberately, like block_stale_pr_branch_date: a branch is named for the operator's day.
    today = datetime.datetime.now().strftime("%m%d")  # noqa: DTZ005 -- see above
    for creation in creations:
        repo = creation.repo_root
        # A directory that resolves to no repository is one git itself will refuse; one outside this checkout is not this policy's business.
        if not repo or not commit_policy.is_inside(repo, root):
            continue
        name = creation.name.strip("'\"")
        if creation.kind in REMOTE_KINDS:
            current = commit_policy.current_branch(repo)
            # An unreadable `ref=` on a `git/refs` POST is a branch this guard cannot name, and so cannot admit.
            if name and name in ("main", "HEAD", current):
                continue
            return _refuse(
                ev,
                "this names a remote branch `%s` that is not the one live branch `%s`."
                % (name, current or "(detached)"),
            )
        if name in commit_policy.local_branches(repo):
            continue
        if _judge_local(ev, creation._replace(name=name), console_top, console_branch, today):
            return hookio.DENY
    return hookio.ALLOW
