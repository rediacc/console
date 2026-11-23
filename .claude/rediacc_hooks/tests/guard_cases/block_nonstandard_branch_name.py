"""The test tables of `block_nonstandard_branch_name`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    ("the 2026-08-26 shape", "git checkout -b 0826-1-prerebase"),
    ("a conforming name", "git checkout -b 0901-1"),
    ("a slashed name is still a name being created", "git checkout -b feature/x"),
    ("switch has its own flag letters", "git switch -c 0901-2-wip"),
    ("a start point is not a name being created", "git checkout -b 0901-3 origin/main"),
    # `git branch` reads are none of this hook's business.
    ("deleting a branch", "git branch -d 0826-1"),
    ("listing branches", "git branch --show-current"),
    ("a plain create", "git branch 0901-4"),
    ("a plain create with a bad name", "git branch prerebase-copy"),
    # The rename form judges the SECOND positional.
    ("a rename into a legal name", "git branch -m old 0901-5"),
    ("a rename into a suffixed one", "git branch -m old 0901-5-prerebase"),
    # The two things the anchor and the stripper exist for.
    ("a variable assignment runs nothing", "SLASH='git checkout -b some/name'"),
    ("a heredoc body is data", "cat > note.md <<'EOF'\ngit checkout -b some/name\nEOF"),
    ("switching to main", "git checkout main"),
    # F1, refused live on 2026-09-25: a quoted grep PATTERN is not a branch being created.
    (
        "F1: a grep for the verbs runs grep",
        'grep -n -e "checkout -b" -e "git branch [a-z0-9]" x.py',
    ),
    ("a wrapper payload is still walked", "sh -c 'git checkout -b feature/x'"),
    ("a remote-looking name is a name being created", "git checkout -b origin/x"),
]
