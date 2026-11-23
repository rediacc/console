"""The test tables of `block_destructive_git_restore`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

# ONE WORLD, AND IT IS A FIXTURE, since #18c7e53c. A lone checkout operand is now judged by asking the repository whether it resolves as a ref, so a golden recorded against the live checkout would freeze whichever branches that machine happens to hold (`git checkout 0826-3` is a ref on a checkout that never pruned it and a pathspec everywhere else). `git-ahead` is `_build_repo`'s pinned world: local `main` and `0831-1`, with `origin/0831-1`.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("default", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
]


EDGE_CASES = load_table("block_destructive_git_restore", "EDGE_CASES")
