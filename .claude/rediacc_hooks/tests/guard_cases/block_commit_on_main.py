"""The test tables of `block_commit_on_main`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("main-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    ("feature-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
]


HOTFIX = 'git commit -m "fix(ci): x [hotfix]\n\nHotfix-Evidence: 12345678" -- a.ts'


EDGE_CASES = [
    ("a plain commit", 'git commit -m "feat(x): y" -- a.ts'),
    ("a valid hotfix", HOTFIX),
    (
        "a hotfix above the file limit",
        'git commit -m "fix: x [hotfix]\n\nHotfix-Evidence: 12345678" -- a b c d e f',
    ),
    ("a hotfix with no evidence", 'git commit -m "fix: x [hotfix]" -- a.ts'),
    (
        "a hotfix whose evidence has no known shape",
        'git commit -m "fix: x [hotfix]\n\nHotfix-Evidence: trust me" -- a.ts',
    ),
    (
        "the ASKED evidence form",
        'git commit -m "fix: x [hotfix]\n\nHotfix-Evidence: ASKED:2026-09-25T10:00Z" -- a.ts',
    ),
    ("a wrapper payload is still judged", "sh -c 'git commit -m \"feat: y\" -- a.ts'"),
    ("a commit in a scratch repo", 'git -C /tmp commit -m "x" -- a'),
    ("prose about committing", "echo 'git commit on main'"),
    ("git log is not a commit", "git log -n 5"),
]
