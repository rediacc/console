"""The test tables of `block_lease_boundary`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import os
import subprocess

from rediacc_hooks.tests.fixtures.guards.loader import load_table


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


EDGE_CASES = load_table("block_lease_boundary", "EDGE_CASES")
