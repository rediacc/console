"""The test tables of `block_push_to_protected_branch`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

# THE THREE GIT WORLDS THE IMPLICIT FORMS DISTINGUISH, same reasoning as block_merge_with_unpushed.py's own ENVS: run against THIS checkout (whatever feature branch a session happens to be on) a bare `git push` always takes the "not main" branch of the fallback logic, so the corpus alone proves nothing about the branch check -- and the defect above would pass
# silently planted, exactly as it did before this was added (test_the_differential_can_fail caught it live on 2026-09-22).
ENVS: list = [
    ("main-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    ("feature-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
    # A FROZEN clone of this checkout rather than the live one, for the reason block_merge_with_unpushed.py:31 records: a shared tree's branch moves under a running differential. Same snapshot, built once per session.
    ("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {}),
]


EDGE_CASES = load_table("block_push_to_protected_branch", "EDGE_CASES")
