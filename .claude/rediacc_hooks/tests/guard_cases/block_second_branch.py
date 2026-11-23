"""The test tables of `block_second_branch`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import os
import subprocess


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
