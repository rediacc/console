"""The test tables of `block_lease_boundary`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

import os
import subprocess


def _lease_world(path):
    """A checkout with one linked tree below its holder; the path returned is the tree, so an event with no `cwd` starts inside it."""
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
    tree = path / ".claude" / "worktrees" / "w"
    for argv in (
        ["init", "-q", "--initial-branch=main"],
        ["commit", "-q", "--allow-empty", "-m", "seed"],
        ["branch", "0923-1"],
        ["worktree", "add", "-q", "--detach", str(tree), "HEAD"],
    ):
        subprocess.run(["git", *argv], cwd=str(path), check=True, capture_output=True, env=env)
    return tree


FIXTURES = {"lease-tree": _lease_world}


ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("lease", {"CLAUDE_PROJECT_DIR": "{FIXTURE:lease-tree}"}, {}),
    ("main-checkout", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
]


EDGE_CASES = [
    ("a push", "git push origin HEAD:0923-1"),
    ("a pin push", "git push origin HEAD:refs/worktrees/x"),
    ("a switch", "git switch main"),
    ("a new branch", "git switch -c x"),
    ("a checkout of a branch", "git checkout 0923-1"),
    ("a cherry-pick", "git cherry-pick HEAD"),
    ("gh pr", "gh pr create --title x --body y"),
    ("a wrapper", "sh -c 'git push origin HEAD:0923-1'"),
    ("control: status", "git status"),
    ("control: log", "git log -1"),
    ("control: prose", "echo git push origin HEAD:0923-1"),
    ("control: a checkout of paths", "git checkout -- x"),
]
