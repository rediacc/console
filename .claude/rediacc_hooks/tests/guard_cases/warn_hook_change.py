"""The test tables of `warn_hook_change`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.guard_cases import _common

_fixture_git = _common.fixture_git


def _repo_with_staged(path, hook_files):
    """A repo whose index holds `hook_files` plus one file that is not a hook.

    The non-hook file is not padding: it is the only thing that proves the `^\\.claude/hooks/` filter is doing any filtering, and a fixture that staged hooks alone would let the port drop the grep and still pass.
    """
    path.mkdir(parents=True)
    _fixture_git(path, "init", "--initial-branch=main", "-q")
    (path / "README.md").write_text("not a hook\n", encoding="utf-8")
    _fixture_git(path, "add", "README.md")
    for name in hook_files:
        target = path / ".claude" / "hooks" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        _fixture_git(path, "add", str(target))
    return path


FIXTURES = {
    # Two hook files, so the port's per-line indentation loop is exercised on more than one record.
    "hooks-staged": lambda p: _repo_with_staged(
        p, ["pre-bash/block-example.sh", "pre-edit/warn-example.sh"]
    ),
    # The same world with nothing under .claude/hooks/ staged: the ALLOW side, and the only reason the grep above is visible to the differential.
    "hooks-clean": lambda p: _repo_with_staged(p, []),
}


# WHY THE LIVE WORKTREE IS NOT ONE OF THESE. The guard's answer is a function of whatever happens to be in THIS checkout's index, and this tree is shared with other sessions and other agents. A `git add` landing between the bash sweep and the Python sweep would be reported here as a port defect, so both variants are controlled worlds built by the builders above.
ENVS: list = [
    (
        "staged",
        {
            "GIT_DIR": "{FIXTURE:hooks-staged}/.git",
            "GIT_WORK_TREE": "{FIXTURE:hooks-staged}",
        },
        {},
    ),
    (
        "clean",
        {
            "GIT_DIR": "{FIXTURE:hooks-clean}/.git",
            "GIT_WORK_TREE": "{FIXTURE:hooks-clean}",
        },
        {},
    ),
]


EDGE_CASES = [
    ("the plain commit", "git commit -m 'fix a guard'"),
    # `case "$CMD" in *"git commit"*)` is an UNANCHORED glob, so a commit in a later clause, in a wrapper, or inside quoted prose all reach the check. That is the original's behaviour and the port must keep it, warts and all.
    ("a commit in a later clause", "git add -A && git commit -m x"),
    ("quoted prose still counts as a commit", "echo 'then git commit -m x'"),
    ("git commit-tree is a substring match too", "git commit-tree HEAD^{tree}"),
    ("a non-commit git verb", "git status"),
    ("no git at all", "ls -la"),
]
