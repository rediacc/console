"""The test tables of `block_adhoc_sanctioned`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    ("the banned watch verb", "gh run watch 123 --exit-status --interval 100"),
    (
        "a hand-rolled poll, whose banned half lives INSIDE quotes",
        'until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do',
    ),
    # The counters from the registry's own rows: a legitimately different command that must NOT match.
    ("reading a run once is not watching it", "gh run view 123 --json conclusion,jobs"),
    ("the sanctioned tool itself", ".ci/scripts/ci/ci-trace.py --wait"),
    # A heredoc body is DATA, so a note quoting a banned recipe is allowed...
    ("a heredoc body is data", "cat > note.md <<'EOF'\ngh run watch 123\nEOF"),
    # ...while the quoted residue is refused, knowingly (operator ruling).
    ("quoted prose is still refused, and that is the ruling", "echo 'gh run watch 123'"),
]
