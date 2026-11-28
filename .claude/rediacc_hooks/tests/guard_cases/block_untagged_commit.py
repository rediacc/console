"""The test tables of `block_untagged_commit`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import os
import subprocess

from rediacc_hooks.tests.fixtures.guards.loader import load_table


def _fixture(path):
    """A checkout on a branch that HAS an epic snapshot.

    Without it the id-validation arm is unreachable: this worktree carries no `agent/pr/<branch>.md`, so `KNOWN` is empty on every case and the guard can only ever answer "missing trailer" or "allowed". The corpus would then have compared two constants for the branch that the 2026-08-27 typo finding exists for.
    """
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )
    path.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--initial-branch=0831-1", "-q"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env=env,
    )
    snap = path / "agent" / "pr"
    snap.mkdir(parents=True)
    (snap / "0831-1.md").write_text(
        "### Port the guards\n\n`PR-TASK: a1b2c3d4`\n\n### Wire the registry\n\n`PR-TASK: 0f9e8d7c`\n",
        encoding="utf-8",
    )
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True, env=env)
    subprocess.run(
        ["git", "commit", "-q", "-m", "seed"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env=env,
    )
    return path


FIXTURES = {"epic-snapshot": _fixture}


ENVS: list = [
    ("snapshot", {"CLAUDE_PROJECT_DIR": "{FIXTURE:epic-snapshot}"}, {}),
    # This checkout's SHAPE, synthetic and pinned since 2026-09-24: a `MMDD-N` branch and an `agent/pr/<branch>.md` in the published format, with no other session able to rewrite either. See `_synthetic_this_worktree` in test_guards_differential.py.
    ("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {}),
    # ON `main`, where a `[hotfix]` needs no trailer (F5 of the commit-policy plan) and anything else still does.
    ("main", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
]


EDGE_CASES = load_table("block_untagged_commit", "EDGE_CASES")
