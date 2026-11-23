"""The test tables of `block_unpushed_submodule_pin`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.guards.block_unpushed_submodule_pin import GITLINK_MODE
from rediacc_hooks.tests.fixtures.guards.git import fixture_git
from rediacc_hooks.tests.fixtures.guards.loader import load_table

_FIXTURE_DATE = "2026-01-01T00:00:00+00:00"


def _fixture_git(cwd, *args):
    return fixture_git(cwd, *args, date=_FIXTURE_DATE)


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


EDGE_CASES = load_table("block_unpushed_submodule_pin", "EDGE_CASES")
