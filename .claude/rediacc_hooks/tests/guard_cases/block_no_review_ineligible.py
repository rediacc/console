"""The test tables of `block_no_review_ineligible`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    ("a code path", 'git commit -m "feat: x [no-review]" -- src/a.ts'),
    ("an agent program", 'git commit -m "docs: x [no-review]" -- .claude/commands/x.md'),
    ("policy", 'git commit -m "docs: x [no-review]" -- CLAUDE.md'),
    ("writing only", 'git commit -m "docs: x [no-review]" -- agent/plans/x.md docs/y.md'),
    (
        "a hotfix is always reviewed",
        'git commit -m "docs: x [hotfix] [no-review]\n\nHotfix-Evidence: 12345678" -- docs/y.md',
    ),
    ("an untagged code commit", 'git commit -m "feat: x" -- src/a.ts'),
    ("prose naming the tag", "echo 'tag it [no-review]'"),
]
