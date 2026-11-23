"""The test tables of `block_git_amend`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    ("the plain shape", "git commit --amend --no-edit"),
    ("the bundled short flag", "git commit -am amend"),
    ("after a separator", "true; git commit --amend"),
    # The two false-positive classes, and the evasion that closing the first one opened.
    (
        "a cat heredoc documenting the rule is data",
        "cat > RULES.md <<'EOF'\ngit commit --amend\nEOF",
    ),
    (
        "a tab-indented terminator really closes the body",
        "cat > R.md <<-'EOF'\n\tgit commit --amend\n\tEOF\ngit commit --amend",
    ),
    (
        "an INTERPRETER heredoc still executes, so it still matches",
        "bash <<EOF\ngit commit --amend\nEOF",
    ),
    ("quoted prose is not a command", "echo 'git commit --amend'"),
    ("a wrapper payload is still scanned", 'sh -c "git commit --amend"'),
    ("an ordinary commit", "git commit -m 'fix(cli): x'"),
    # Rule T, A0 L3: an unquoted-delimiter heredoc body expands its substitutions, so this amends; the quoted-delimiter twin just below it is data and stays allowed.
    (
        "an unquoted cat heredoc runs its substitution",
        "cat > R.md <<EOF\n$(git commit --amend --no-edit)\nEOF",
    ),
    (
        "a quoted cat heredoc keeps its substitution as data",
        "cat > R.md <<'EOF'\n$(git commit --amend --no-edit)\nEOF",
    ),
    # Rule T, the 2026-09-03 env-prefix class that shellscan closed for seven guards: this view never had the strip, so one `FOO=bar ` token still hid the amend here.
    ("an env prefix does not hide the command", "FOO=bar git commit --amend --no-edit"),
    # Rule T, A0 L7: quote removal applies to the command word.
    ("a quoted command word is still git", '"git" commit --amend --no-edit'),
]
