"""The test tables of `block_commit_on_main`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("main-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    ("feature-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
]


HOTFIX = 'git commit -m "fix(ci): x [hotfix]\n\nHotfix-Evidence: 12345678" -- a.ts'


EDGE_CASES = load_table("block_commit_on_main", "EDGE_CASES")
