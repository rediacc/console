"""The test tables of `block_ci_skip_token`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    ("[skip ci]", 'git commit -m "chore: x [skip ci]" -- a'),
    ("[ci skip]", 'git commit -m "chore: x [ci skip]" -- a'),
    ("[no ci]", 'git commit -m "chore: x [no ci]" -- a'),
    ("[skip actions]", 'git commit -m "chore: x [skip actions]" -- a'),
    ("[actions skip]", 'git commit -m "chore: x [actions skip]" -- a'),
    ("the rejected [no-ci]", 'git commit -m "chore: x [no-ci]" -- a'),
    ("the trailer form", 'git commit -m "chore: x\n\nskip-checks: true" -- a'),
    ("a --trailer value", 'git commit -m "chore: x" --trailer "skip-checks: true" -- a'),
    ("a heredoc message", "git commit -F - -- a <<'EOF'\nchore: x [skip ci]\nEOF"),
    ("a clean commit", 'git commit -m "chore: x" -- a'),
    ("prose naming the token", "echo 'never write [skip ci]'"),
    ("git log --grep", "git log --grep '[skip ci]'"),
    ("a scratch repo", 'git -C /tmp commit -m "x [skip ci]" -- a'),
]
