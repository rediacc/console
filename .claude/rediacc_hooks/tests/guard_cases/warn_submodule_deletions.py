"""The test tables of `warn_submodule_deletions`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

from rediacc_hooks.tests.guard_cases import _common

_fixture_git = _common.fixture_git


# The four states one .gitmodules entry can be in, in one tree: sub every tracked file staged for deletion -- the loudest arm partial one of three, so the loud arm must NOT fire clean a real submodule with nothing staged, skipped by the `-n` test gone a path with no checkout at all, skipped by the `-e` test
_SUBMODULES = (
    ("sub", ["sub/a.txt", "sub/b.txt"], ["sub/a.txt", "sub/b.txt"]),
    ("partial", ["partial/a.txt", "partial/b.txt", "partial/c.txt"], ["partial/a.txt"]),
    ("clean", ["clean/x.txt"], []),
)


def _submodule_tree(path):
    """A superproject with four .gitmodules entries in four different states.

    WHY THE FILES SIT UNDER A DIRECTORY NAMED AFTER THE SUBMODULE, which looks redundant and is not. The differential can only reach this guard through the environment, and the only lever that moves `git rev-parse --show-toplevel` away from this checkout is `GIT_WORK_TREE`. With it exported, `git -C sub` still DISCOVERS `sub/.git` (so each submodule's own index and HEAD are read,
    which is the whole point), but git computes the cwd's prefix against the exported work tree rather than against the discovered repo -- measured 2026-09-06, `git -C sub rev-parse --show-prefix` answers `sub/`. `ls-tree -r HEAD` honours that prefix and `diff --cached` does not, so a submodule whose files sat at its own root would report `2 of 0 tracked file(s)` and the loudest
    arm could never fire. Putting the tracked files under `sub/` inside the submodule cancels the prefix, and the guard then sees exactly the counts it would see in a real superproject.
    """
    path.mkdir(parents=True)
    _fixture_git(path, "init", "-q", "--initial-branch=main")
    for name, files, deleted in _SUBMODULES:
        sub = path / name
        sub.mkdir()
        _fixture_git(sub, "init", "-q", "--initial-branch=main")
        for rel in files:
            target = sub / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x\n", encoding="utf-8")
        _fixture_git(sub, "add", "-A")
        _fixture_git(sub, "commit", "-qm", "seed")
        for rel in deleted:
            _fixture_git(sub, "rm", "-q", rel)
    (path / ".gitmodules").write_text(
        "".join(
            '[submodule "%s"]\n\tpath = %s\n\turl = ./%s\n' % (n, n, n)
            for n in ("sub", "partial", "clean", "gone")
        ),
        encoding="utf-8",
    )
    (path / "top.txt").write_text("x\n", encoding="utf-8")
    _fixture_git(path, "add", ".gitmodules", "top.txt")
    _fixture_git(path, "commit", "-qm", "seed")
    return path


FIXTURES = {"submodule-deletions": _submodule_tree}


# GIT_WORK_TREE and NOT CLAUDE_PROJECT_DIR: this guard never reads that variable. It resolves its own root with `git rev-parse --show-toplevel` from whatever directory the harness invoked it in, so the environment is the only place a controlled world can be handed to it.
ENVS = [("submodules", {"GIT_WORK_TREE": "{FIXTURE:submodule-deletions}"}, {})]


EDGE_CASES = [
    ("the plain commit", "git commit -m x"),
    ("a submodule commit typed from the parent", "git -C private/renet commit -m x"),
    ("a commit in a later clause", "git add -A && git commit -m x"),
    # The finding in the module docstring, pinned. Unlike warn-stale-index.sh this guard does not route through lib/command-scan.sh, so prose reaches the scan.
    ("quoted prose reaches the scan", "echo 'git commit -m x'"),
    ("commit is a whole word", "git commitment"),
    ("a different git verb", "git status"),
    ("no git at all", "ls -la"),
]
