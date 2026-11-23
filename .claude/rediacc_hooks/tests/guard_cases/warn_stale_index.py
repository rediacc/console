"""The test tables of `warn_stale_index`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.guard_cases import _common

_fixture_git = _common.fixture_git


def _seeded(path, names):
    path.mkdir(parents=True)
    _fixture_git(path, "init", "-q", "--initial-branch=main")
    for name in names:
        (path / name).write_text("v1\n", encoding="utf-8")
    _fixture_git(path, "add", "-A")
    _fixture_git(path, "commit", "-qm", "seed")
    return path


def _stale_tree(path):
    """staged {a, b}, unstaged {a, c} -- the intersection is exactly {a}.

    `b` and `c` are not padding: without `b` the intersection would equal the staged set and without `c` it would equal the unstaged set, and a port that printed either whole set instead of the intersection would still pass.
    """
    _seeded(path, ["a.txt", "b.txt", "c.txt"])
    (path / "a.txt").write_text("v2\n", encoding="utf-8")
    (path / "b.txt").write_text("v2\n", encoding="utf-8")
    _fixture_git(path, "add", "a.txt", "b.txt")
    # THEN edited, which is the whole defect this guard exists for.
    (path / "a.txt").write_text("v3\n", encoding="utf-8")
    (path / "c.txt").write_text("v2\n", encoding="utf-8")
    return path


def _disjoint_tree(path):
    """staged {b}, unstaged {c}: both sets non-empty, no overlap.

    The ALLOW side that a fixture with nothing staged could not provide, since that one leaves through the earlier `-n` test and never reaches `comm`.
    """
    _seeded(path, ["a.txt", "b.txt", "c.txt"])
    (path / "b.txt").write_text("v2\n", encoding="utf-8")
    _fixture_git(path, "add", "b.txt")
    (path / "c.txt").write_text("v2\n", encoding="utf-8")
    return path


FIXTURES = {"stale-index": _stale_tree, "disjoint-index": _disjoint_tree}


# BOTH variables, not just GIT_WORK_TREE. This guard's `git diff` calls take no `-C` and run in whatever directory the harness invoked it in, so leaving GIT_DIR to discovery would diff THIS checkout's index against the fixture's work tree -- a comparison of two unrelated trees, and a very large one.
ENVS = [
    (
        "stale",
        {
            "GIT_DIR": "{FIXTURE:stale-index}/.git",
            "GIT_WORK_TREE": "{FIXTURE:stale-index}",
        },
        {},
    ),
    (
        "disjoint",
        {
            "GIT_DIR": "{FIXTURE:disjoint-index}/.git",
            "GIT_WORK_TREE": "{FIXTURE:disjoint-index}",
        },
        {},
    ),
]


EDGE_CASES = [
    ("the plain commit", "git commit -m x"),
    # Defect 1 above, in the form it took.
    ("the -F form the first defect took", "git commit -F /tmp/msg.txt"),
    ("a commit after &&", "git add -A && git commit -m x"),
    # `-a` and `--all` commit the WORKING TREE for those paths.
    ("-a takes the working tree", "git commit -a -m x"),
    ("--all takes the working tree", "git commit --all -m x"),
    # The mention-vs-target anchor, in both directions.
    ("quoted prose is not a command", "echo 'do not run git commit here'"),
    ("a wrapper payload is still a command", "sh -c 'git commit -m x'"),
    ("a different git verb", "git status"),
]
