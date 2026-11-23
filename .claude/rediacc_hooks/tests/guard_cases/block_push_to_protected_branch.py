"""The test tables of `block_push_to_protected_branch`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

# THE THREE GIT WORLDS THE IMPLICIT FORMS DISTINGUISH, same reasoning as block_merge_with_unpushed.py's own ENVS: run against THIS checkout (whatever feature branch a session happens to be on) a bare `git push` always takes the "not main" branch of the fallback logic, so the corpus alone proves nothing about the branch check -- and the defect above would pass
# silently planted, exactly as it did before this was added (test_the_differential_can_fail caught it live on 2026-09-22).
ENVS = [
    ("main-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    ("feature-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
    # A FROZEN clone of this checkout rather than the live one, for the reason block_merge_with_unpushed.py:31 records: a shared tree's branch moves under a running differential. Same snapshot, built once per session.
    ("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {}),
]


EDGE_CASES = [
    ("the incident's own shape", "git push origin HEAD:main"),
    ("a bare destination name", "git push origin main"),
    ("an explicit source, destination main", "git push origin 0914-1:main"),
    ("the refs-qualified long form", "git push origin refs/heads/main"),
    ("the empty-source delete form", "git push origin :main"),
    ("the flagged delete form", "git push origin --delete main"),
    ("--all pushes every branch, main included", "git push --all origin"),
    ("a bare push with no refspec at all", "git push"),
    ("a remote with no refspec", "git push origin"),
    ("HEAD with no colon aliases the current branch's own name", "git push origin HEAD"),
    ("a wrapper payload is still scanned", 'eval "git push origin main"'),
    # Controls: none of these are this guard's business.
    ("an ordinary push to a feature branch", "git push origin 0914-1"),
    ("a branch merely prefixed with main", "git push origin main-2"),
    ("a branch merely suffixed onto main", "git push origin not-main"),
    ("an explicit non-main destination overrides ambiguity", "git push origin feature-x"),
    ("a dry run publishes nothing", "git push --dry-run origin main"),
    ("tags only, no branch ref moves", "git push --tags origin"),
    ("prose about pushing is not a push", "echo 'never push straight to main'"),
    ("git pull is not git push", "git pull --rebase"),
    (
        "cd into a submodule pushing its own feature branch",
        "cd private/renet && git push origin 0914-1",
    ),
    # Global options before `push` (measured rc 0 on 2026-10-02), and a dry run beside a real push.
    ("-C before push, destination main", "git -C . push origin HEAD:main"),
    ("-c before push, destination main", "git -c a=b push origin main"),
    ("a dry run beside a real push", "git push --dry-run origin x; git push origin HEAD:main"),
    # M2: the fallback's shape refused before any gh read (no PR world here, so every spelling refuses).
    ("M2 the fallback shape with --force", "git push --force origin 0914-1:main"),
    ("M2 the fallback shape with two refspecs", "git push origin 0914-1:main 0914-1"),
    # The GitLab mirror push: no fixture here carries a `gitlab` remote, so every spelling refuses; the admitted worlds are in this guard's own suite.
    ("mirror the 6b spelling", "git push gitlab refs/heads/main:refs/heads/main --follow-tags"),
    ("mirror with --force", "git push --force gitlab main:main"),
    ("mirror a bare --mirror push", "git push --mirror gitlab"),
]
