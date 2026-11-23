"""The test tables of `block_untagged_commit`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

import os
import subprocess


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


ENVS = [
    ("snapshot", {"CLAUDE_PROJECT_DIR": "{FIXTURE:epic-snapshot}"}, {}),
    # This checkout's SHAPE, synthetic and pinned since 2026-09-24: a `MMDD-N` branch and an `agent/pr/<branch>.md` in the published format, with no other session able to rewrite either. See `_synthetic_this_worktree` in test_guards_differential.py.
    ("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {}),
    # ON `main`, where a `[hotfix]` needs no trailer (F5 of the commit-policy plan) and anything else still does.
    ("main", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
]


EDGE_CASES = [
    ("no trailer at all", 'git commit -m "feat(x): a change"'),
    ("a real trailer", 'git commit -m "feat(x): a change\n\nPR-TASK: a1b2c3d4"'),
    ("an escaped-newline trailer", 'git commit -m "feat(x): a change\\n\\nPR-TASK: a1b2c3d4"'),
    # The 2026-08-27 typo finding: one character off, and the commit LOOKS tagged.
    ("an id naming no epic", 'git commit -m "feat(x): a\n\nPR-TASK: f2757831"'),
    # The `-F` shapes the same finding widened.
    (
        "-F - with a heredoc is readable",
        "git commit -F - <<'EOF'\nfeat(x): a\n\nPR-TASK: a1b2c3d4\nEOF",
    ),
    ("-F - on a pipe is not readable, so allowed", "cat msg.txt | git commit -F -"),
    ("-F on a file that does not exist", "git commit -F /nonexistent-msg.txt"),
    # Prose about committing is not a commit.
    ("prose naming the trailer", "echo 'add a PR-TASK: a1b2c3d4 trailer'"),
    ("git log is not git commit", "git log --grep='^PR-TASK: a1b2c3d4'"),
    # A foreign checkout's commits are not this repo's epics' business.
    ("a commit in another tree", 'cd /tmp && git commit -m "x"'),
    ("git -C into another tree", 'git -C /tmp commit -m "x"'),
    # A TAB after `-C` is a blank like any other since the Rule T fix to shellscan.target_root (A4); /tmp is not a repository, so this and the space form above both judge this tree.
    ("git -C with a TAB is still a -C", 'git -C\t/tmp commit -m "x"'),
    # F5: a hotfix on `main` has no epic to name. Off `main` the tag buys nothing here.
    (
        "a hotfix names no epic",
        'git commit -m "fix(ci): x [hotfix]\n\nHotfix-Evidence: 12345678" -- a.ts',
    ),
]
