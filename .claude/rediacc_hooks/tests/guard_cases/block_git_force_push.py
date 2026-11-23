"""The test tables of `block_git_force_push`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import os
import subprocess

from rediacc_hooks import commit_policy


def _two_trees(path, tree):
    """A main checkout on the development branch `0831-2` and its landing tree, a linked tree at the sibling `<main>-landing` holding the PR branch `0831-1`, bound by the landing record (box LT3 of agent/plans/PLAN-two-track-merge-dev.md). Answers the tree named by `tree`."""
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
    main = path / "console"
    landing = path / "console-landing"
    main.mkdir(parents=True)
    for argv in (
        ["init", "-q", "--initial-branch=main"],
        ["commit", "-q", "--allow-empty", "-m", "seed"],
        ["branch", "0831-1"],
        ["worktree", "add", "-q", str(landing), "0831-1"],
        ["checkout", "-q", "-b", "0831-2"],
    ):
        subprocess.run(["git", *argv], cwd=str(main), check=True, capture_output=True, env=env)
    commit_policy.write_landing_record(str(main), str(landing), "0831-1")
    return landing if tree == "landing" else main


FIXTURES = {
    "landing-tree": lambda p: _two_trees(p, "landing"),
    "development-tree": lambda p: _two_trees(p, "development"),
}


# THE TWO GIT WORLDS THE LEASE ARM DISTINGUISHES. `default` keeps its label and points at a checkout on `main`, where no lease is admitted, so every record the cross-corpus froze before M3 answers as it did. `live-branch` is a checkout on `0831-1`, the one live branch, where a lease naming it is admitted. Without the second world no case could reach the allow arm, and without the first the corpus would read the live checkout's branch.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("default", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    ("live-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
    # LT3: two trees, one live branch each. Each tree's lease admits its own branch only because `commit_policy.live_branches` leaves out the branch the landing record binds to the other tree; without the binding both worlds hold two live branches and every lease is refused. The M3 cases below are the matrix: `M3 lease to the live branch` (`0831-1`) is admitted in `landing-tree` and `live-branch` only, and `M3 lease to another branch` (`0831-2`) in `development-tree` only.
    ("landing-tree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:landing-tree}"}, {}),
    ("development-tree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:development-tree}"}, {}),
]


EDGE_CASES = [
    ("the obvious flag", "git push --force origin main"),
    ("the short flag", "git push -f origin main"),
    ("the leased flag", "git push --force-with-lease"),
    # The 2026-08-23 hole, both halves.
    ("a mirror push forces every ref", "git push --mirror origin"),
    ("a shorthand plus refspec forces one", "git push origin +main:main"),
    ("the refs-qualified long form", "git push origin +refs/heads/main"),
    # The control that keeps the widening honest.
    ("a plus INSIDE a token is a legal branch name", "git push origin HEAD:refs/heads/feature+x"),
    ("a plain push", "git push origin main"),
    # The 2026-08-30 routing exists for these two.
    ("prose about force-pushing is not one", "echo 'never git push --force'"),
    ("a wrapper payload is still scanned", 'eval "git push --force origin main"'),
    # RULE T (PLAN-retire-bash-oracles A4): A0's fail-open list, measured rc 0 on 2026-09-24 and refused since `shellscan.lifted_commands`. Every shape below is a push bash RUNS; the prose, data and print-only twins after them stay allowed.
    ("L1 an assignment's substitution runs", "x=$(git push --force origin main)"),
    ("L1 an assignment's backticks run", "x=`git push --force origin main`"),
    ("L2 a substitution inside double quotes runs", 'echo "$(git push --force origin main)"'),
    (
        "L3 an unquoted heredoc body expands",
        "cat > R.md <<EOF\n$(git push --force origin main)\nEOF",
    ),
    ("L4 a shell reading a heredoc runs it", "bash <<'EOF'\ngit push --force origin main\nEOF"),
    ("L4 a shell reading a here-string runs it", "bash <<< 'git push --force origin main'"),
    ("L5 a here-string swallows no later line", "cat <<<x\ngit push --force origin main"),
    (
        "L6 an apostrophe inside double quotes pairs with nothing",
        "echo \"it's\"; git push --force origin main; echo 'y'",
    ),
    ("L7 a quoted command word is still git", '"git" push --force origin main'),
    ("L7 an escaped command word is still git", "\\git push --force origin main"),
    ("L8 a backslash-newline joins the command", "git push \\\n--force origin main"),
    ("L9 a brace group", "{ git push --force origin main; }"),
    ("L9 a leading redirect", ">/dev/null git push --force origin main"),
    (
        "L9 sudo and time run the next word",
        "sudo git push -f origin main; time git push --mirror origin",
    ),
    ("L10 c inside a short-flag bundle", "bash -ce 'git push --force origin main'"),
    ("L11 the second wrapper on a line", "sh -c true; sh -c 'git push --force origin main'"),
    (
        "control: a quoted heredoc body is data",
        "cat > R.md <<'EOF'\n$(git push --force origin main)\nEOF",
    ),
    (
        "control: double-quoted prose is not a push",
        'git commit -m "never git push --force origin main"',
    ),
    ("control: command -v only prints", "command -v git push --force"),
    # M3 (PLAN-plan-per-pr-loop, operator ruling 2026-10-02). `0831-1` is the live branch of the `live-branch` world and absent from the `default` (main) world, so each admitted case is refused there: the two worlds are the two directions.
    ("M3 lease to the live branch", "git push --force-with-lease origin 0831-1"),
    (
        "M3 lease with an expected sha",
        "git push --force-with-lease=0831-1:0123456789abcdef0123456789abcdef01234567 origin 0831-1",
    ),
    ("M3 lease of HEAD to the live branch", "git push --force-with-lease origin HEAD:0831-1"),
    ("M3 lease in a wrapper payload", "sh -c 'git push --force-with-lease origin 0831-1'"),
    ("M3 lease to main", "git push --force-with-lease origin main"),
    ("M3 lease of HEAD to main", "git push --force-with-lease origin HEAD:main"),
    ("M3 lease to another branch", "git push --force-with-lease origin 0831-2"),
    ("M3 lease beside a plus refspec", "git push --force-with-lease origin +0831-1"),
    ("M3 lease beside --force", "git push --force --force-with-lease origin 0831-1"),
    ("M3 lease naming another ref", "git push --force-with-lease=main origin 0831-1"),
    ("M3 lease to two refspecs", "git push --force-with-lease origin 0831-1 0831-2"),
    ("M3 lease to another remote", "git push --force-with-lease upstream 0831-1"),
    ("M3 lease in a repository outside", "git -C /tmp push --force-with-lease origin 0831-1"),
    ("M3 lease with --all", "git push --force-with-lease --all origin"),
    ("M3 lease through -C to the live branch", "git -C . push --force-with-lease origin 0831-1"),
    # #18c7e53c A-1: deleting the checked-out branch. Refused in the `live-branch` world, where `0831-1` is checked out; in the `default` world (on main) the same line is pr-merge step 7's post-merge cleanup and stays allowed. The two worlds are the two directions.
    ("A1 --delete of the checked-out branch", "git push origin --delete 0831-1"),
    ("A1 --delete before the remote", "git push --delete origin 0831-1"),
    ("A1 -d of the checked-out branch", "git push -d origin 0831-1"),
    ("A1 an empty-source refspec deletes", "git push origin :0831-1"),
    ("A1 the refs/heads spelling", "git push origin :refs/heads/0831-1"),
    ("A1 --delete beside the lease", "git push --force-with-lease --delete origin 0831-1"),
    ("A1 a deletion behind a cd", "cd . && git push origin --delete 0831-1"),
    ("A1 --prune deletes what no line shows", "git push --prune origin"),
    ("A1 a deleted name the walk cannot read", 'git push origin --delete "$B"'),
    ("A1 control: --no-delete undoes -d", "git push -d --no-delete origin 0831-1"),
    ("A1 control: a branch no checkout names", "git push origin --delete 0101-9"),
    ("A1 control: the matching refspec is no deletion", "git push origin :"),
    ("A1 control: a plain push of the live branch", "git push origin 0831-1"),
    # A global option between `git` and `push` matched nothing until 2026-10-02 (both measured rc 0 then).
    ("a -C global option before push", "git -C . push --force origin main"),
    ("a -c global option before push", "git -c a=b push -f origin x"),
]
