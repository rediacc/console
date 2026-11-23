"""The test tables of `block_landing_one_way`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

import os
import subprocess

from rediacc_hooks import commit_policy

# ---- the differential's world: a main checkout on the development branch 1121-1 (one development-only commit) and a linked landing tree on 1120-1, bound by the landing record ----
_FIXED_ENV = {
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _landing_world(path):
    """`path`/main on 1121-1 (seed, then `dev`), `path`/landing a linked tree on 1120-1 at seed, and the record binding it; the landing tree is returned, so an event with no `cwd` starts inside it."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(_FIXED_ENV)
    main, landing = path / "main", path / "landing"
    main.mkdir(parents=True)
    for argv in (
        ["init", "-q", "--initial-branch=main"],
        ["commit", "-q", "--allow-empty", "-m", "seed"],
        ["worktree", "add", "-q", "-b", "1120-1", str(landing), "HEAD"],
        ["checkout", "-q", "-b", "1121-1"],
        ["commit", "-q", "--allow-empty", "-m", "dev"],
    ):
        subprocess.run(["git", *argv], cwd=str(main), check=True, capture_output=True, env=env)
    commit_policy.write_landing_record(str(main), str(landing), "1120-1")
    return os.path.realpath(landing)


FIXTURES = {"landing-world": _landing_world}


ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("landing", {"CLAUDE_PROJECT_DIR": "{FIXTURE:landing-world}"}, {}),
]


EDGE_CASES = [
    ("rebase onto development", "git rebase 1121-1"),
    ("merge development", "git merge --ff-only 1121-1"),
    ("cherry-pick development", "git cherry-pick 1121-1"),
    ("reset to development", "git reset --hard 1121-1"),
    ("pull development", "git pull origin 1121-1"),
    ("a range ending at development", "git cherry-pick 1120-1..1121-1"),
    ("control: -C into the main checkout", "git -C ../main rebase 1121-1"),
    ("control: rebase continue", "git rebase --continue"),
    ("control: reset to HEAD", "git reset --hard HEAD"),
    ("control: merge main", "git merge main"),
    ("control: push the landing branch", "git push origin 1120-1"),
    ("control: push the development branch", "git push origin 1121-1"),
    ("control: prose", "echo git merge 1121-1"),
    ("control: status", "git status"),
]
