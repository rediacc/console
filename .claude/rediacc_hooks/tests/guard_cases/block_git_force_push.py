"""The test tables of `block_git_force_push`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import os
import subprocess

from rediacc_hooks import commit_policy
from rediacc_hooks.tests.fixtures.guards.loader import load_table


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


EDGE_CASES = load_table("block_git_force_push", "EDGE_CASES")
