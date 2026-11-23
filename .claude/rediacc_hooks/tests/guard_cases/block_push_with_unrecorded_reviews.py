"""The test tables of `block_push_with_unrecorded_reviews`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

import os
import pathlib
import subprocess

from rediacc_hooks.guards.block_push_with_unrecorded_reviews import _load_reviewer
from rediacc_hooks.tests.fixtures.guards.loader import load_table


def _fixture_env():
    return dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )


def _branch_world(path, reviewed):
    """A checkout on branch 0930-1 with one commit past `origin/main`, and, when `reviewed`, a clean committed review of it.

    The review file is written in the reviewer's own format through `wl_review.render`, so the world needs no model. Without these worlds every edge case would be judged against whatever this shared tree holds when the suite runs, and the guard's DEFECT could not be shown to change any answer.
    """
    path = pathlib.Path(path)
    origin = path.parent / (path.name + "-origin.git")
    env = _fixture_env()

    def git(*args):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, env=env)

    path.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", "--bare", str(origin)], check=True, capture_output=True, env=env
    )
    git("init", "-q", "--initial-branch=main")
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    git("add", "seed.txt")
    git("commit", "-q", "-m", "seed")
    git("remote", "add", "origin", str(origin))
    git("push", "-q", "origin", "main")
    git("checkout", "-q", "-b", "0930-1")
    (path / "f.py").write_text("a = 1\n", encoding="utf-8")
    git("add", "f.py")
    git("commit", "-q", "-m", "fix(x): y")
    if reviewed:
        rv = _load_reviewer()
        sha = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout.strip()
        if not sha:
            raise RuntimeError("git rev-parse HEAD printed nothing in the fixture repo")
        review = rv.Review(
            sha=sha,
            subject="fix(x): y",
            branch="0930-1",
            reviewed_at="2026-10-02T00:00:00Z",
            model="m",
        )
        target = rv.review_path(path, "0930-1", sha)
        rv.write_atomic(target, rv.render(review))
        git("add", "--", str(target.relative_to(path)))
        git("commit", "-q", "-m", "chore(reviews): record")
    return path


FIXTURES = {
    "push-unreviewed": lambda p: _branch_world(p, reviewed=False),
    "push-reviewed": lambda p: _branch_world(p, reviewed=True),
}


ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (name, {"CLAUDE_PROJECT_DIR": "{FIXTURE:%s}" % name}, {}) for name in sorted(FIXTURES)
]


EDGE_CASES = load_table("block_push_with_unrecorded_reviews", "EDGE_CASES")
