"""The test tables of `block_merge_with_unpushed`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.wellknown import GH_REPO, RENET_REPO

# THE THREE GIT WORLDS THIS GUARD DISTINGUISHES, and it distinguishes none of them inside a feature worktree. Run against this checkout it fails open on every input, because no `origin/<branch>` ref exists here -- so the whole corpus would have compared two constants. `test_every_guard_discriminates` said so on the first run, which is what these are an answer to.
ENVS: list = [
    ("ahead", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
    ("synced", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-synced}"}, {}),
    ("main", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    # This checkout's SHAPE, never the checkout itself: a real-looking branch with history and a remote-tracking ref behind it. The live spelling was retired on 2026-09-22 after the measured divergence (66 unpushed commits from bash, 67 from the port), and the per-session clone that replaced it on 2026-09-24, because a golden cannot freeze a tree that moves. See `_synthetic_this_worktree` in test_guards_differential.py.
    ("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {}),
]


EDGE_CASES = [
    ("the verb at a command position", "gh pr merge 42"),
    # `gh pr view`, `gh pr list`, and a merge typed inside a heredoc that documents this hook are all none of its business.
    ("a different pr subcommand", "gh pr view 42"),
    ("a merge for another repository", ("gh pr merge 42 --repo " + RENET_REPO)),
    ("a merge for this repository, named", ("gh pr merge 42 --repo " + GH_REPO)),
    ("--repo with an equals sign", ("gh pr merge 42 --repo=" + RENET_REPO)),
    ("the verb inside quoted prose", "echo 'run gh pr merge when green'"),
]
