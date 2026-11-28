"""The test tables of `block_merge_with_unpushed`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

# THE THREE GIT WORLDS THIS GUARD DISTINGUISHES, and it distinguishes none of them inside a feature worktree. Run against this checkout it fails open on every input, because no `origin/<branch>` ref exists here -- so the whole corpus would have compared two constants. `test_every_guard_discriminates` said so on the first run, which is what these are an answer to.
ENVS: list = [
    ("ahead", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
    ("synced", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-synced}"}, {}),
    ("main", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    # This checkout's SHAPE, never the checkout itself: a real-looking branch with history and a remote-tracking ref behind it. The live spelling was retired on 2026-09-22 after the measured divergence (66 unpushed commits from bash, 67 from the port), and the per-session clone that replaced it on 2026-09-24, because a golden cannot freeze a tree that moves. See `_synthetic_this_worktree` in test_guards_differential.py.
    ("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {}),
]


EDGE_CASES = load_table("block_merge_with_unpushed", "EDGE_CASES")
