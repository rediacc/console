"""The test tables of `block_unpushed_submodule_pin`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

import os
import subprocess

from rediacc_hooks.guards.block_unpushed_submodule_pin import GITLINK_MODE

_FIXTURE_DATE = "2026-01-01T00:00:00+00:00"


def _fixture_git(cwd, *args):

    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_AUTHOR_DATE=_FIXTURE_DATE,
        GIT_COMMITTER_DATE=_FIXTURE_DATE,
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
    )
    done = subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True, env=env
    )
    return done.stdout.strip()


def _pinned_world(path, published):
    """The 6a94a96a9 shape: branch `0923-1` bumps `private/renet` from a published sha to a local-only one.

    Remote-tracking refs are written with `update-ref`, never by pushing: a fixture that pushed would itself be a push this chain judges. `published=True` is the same world after `git -C private/renet push`: the pinned sha is then reachable from a remote-tracking branch.
    """
    path.mkdir(parents=True)
    _fixture_git(path, "init", "-q", "--initial-branch=main")
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _fixture_git(path, "add", "seed.txt")
    sub = path / "private" / "renet"
    sub.mkdir(parents=True)
    _fixture_git(sub, "init", "-q", "--initial-branch=main")
    _fixture_git(sub, "commit", "-q", "--allow-empty", "-m", "published")
    old = _fixture_git(sub, "rev-parse", "HEAD")
    if not old:
        raise RuntimeError("fixture: rev-parse HEAD printed nothing in %s" % sub)
    _fixture_git(sub, "update-ref", "refs/remotes/origin/main", old)
    _fixture_git(sub, "checkout", "-q", "-b", "0923-1")
    _fixture_git(sub, "commit", "-q", "--allow-empty", "-m", "local only")
    new = _fixture_git(sub, "rev-parse", "HEAD")
    if not new:
        raise RuntimeError("fixture: rev-parse HEAD printed nothing in %s" % sub)
    if published:
        _fixture_git(sub, "update-ref", "refs/remotes/origin/0923-1", new)
    _fixture_git(
        path, "update-index", "--add", "--cacheinfo", "%s,%s,private/renet" % (GITLINK_MODE, old)
    )
    _fixture_git(path, "commit", "-q", "-m", "pin published")
    _fixture_git(path, "update-ref", "refs/remotes/origin/main", "HEAD")
    _fixture_git(path, "checkout", "-q", "-b", "0923-1")
    _fixture_git(path, "update-index", "--cacheinfo", "%s,%s,private/renet" % (GITLINK_MODE, new))
    _fixture_git(path, "commit", "-q", "-m", "bump renet")
    return path


FIXTURES = {
    "submodule-pin-unpushed": lambda p: _pinned_world(p, published=False),
    "submodule-pin-pushed": lambda p: _pinned_world(p, published=True),
}


ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("pin-unpushed", {"CLAUDE_PROJECT_DIR": "{FIXTURE:submodule-pin-unpushed}"}, {}),
    ("pin-pushed", {"CLAUDE_PROJECT_DIR": "{FIXTURE:submodule-pin-pushed}"}, {}),
    ("no-submodule", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
]


EDGE_CASES = [
    ("a plain push of the branch", "git push origin 0923-1"),
    ("a bare push", "git push"),
    ("an explicit refspec", "git push origin HEAD:0923-1"),
    ("a forced push is still a push", "git push --force-with-lease origin 0923-1"),
    ("a wrapper payload is still scanned", "sh -c 'git push origin 0923-1'"),
    # Controls: none of these publish a console tip.
    ("a dry run", "git push --dry-run origin 0923-1"),
    ("a delete", "git push origin --delete 0923-1"),
    ("tags only", "git push --tags origin"),
    ("prose about pushing", "echo 'git push origin 0923-1 once renet is up'"),
    ("git pull is not git push", "git pull --rebase"),
    ("a push inside the submodule, by -C", "git -C private/renet push origin 0923-1"),
    ("a push inside the submodule, by cd", "cd private/renet && git push origin 0923-1"),
    ("a push in another tree", "cd /tmp && git push"),
]
