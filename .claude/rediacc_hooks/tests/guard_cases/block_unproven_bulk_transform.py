"""The test tables of `block_unproven_bulk_transform`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import subprocess

from rediacc_hooks.guards.block_unproven_bulk_transform import BULK_FILE_THRESHOLD

EDGE_CASES = [
    ("a bulk commit with no proof quoted", 'git commit -m "reflow the tree"'),
    ("a small commit, well under threshold", 'git commit -m "fix: a small thing"'),
    ("a plain command is not a target", "ls -la"),
    ("gh pr view is not a write", "gh pr view 1"),
    ("git log is not git commit", 'git log --grep "shape_cluster_diff.py"'),
]


def _bulk_staged_world(target):
    """A scratch repo with a bulk-sized change already staged, so the commit branch has something to refuse."""
    target.mkdir(parents=True, exist_ok=True)
    quiet = {
        "capture_output": True,
        "env": {
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": "/nonexistent",
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    }

    def run_git(*args):
        subprocess.run(["git", "-C", str(target), *args], check=True, **quiet)

    run_git("init", "-q", "-b", "main")
    (target / "base.txt").write_text("x\n", encoding="utf-8")
    run_git("add", ".")
    run_git("commit", "-q", "-m", "base")
    for i in range(BULK_FILE_THRESHOLD + 2):
        (target / ("bulk-%02d.py" % i)).write_text("x = %d\n" % i, encoding="utf-8")
    run_git("add", ".")
    return target


FIXTURES = {"bulk-staged": _bulk_staged_world}


# CLAUDE_PROJECT_DIR is the guard's fallback working directory when the payload carries none, so pointing it at the fixture is what puts the staged files under the commit case.
ENVS = [("bulk-staged", {"CLAUDE_PROJECT_DIR": "{FIXTURE:bulk-staged}"}, {})]
