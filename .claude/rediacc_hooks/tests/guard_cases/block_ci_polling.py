"""The test tables of `block_ci_polling`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

EDGE_CASES = [
    # The 2026-08-25 ruling, pinned here as well as in the suite: prose fires.
    ("prose in a heredoc still fires", "cat <<EOF\nsleep 60 && gh run list\nEOF"),
    ("quoted prose still fires", "echo 'sleep 60; gh run view 1'"),
    # The shapes that must NOT fire, which is the half a block-only corpus cannot see.
    ("a wait with no gh after it", "sleep 60 && echo done"),
    ("gh run view with no wait before it", "gh run view 123"),
    ("a pipe between them is not the separator this matches", "sleep 60 | gh run list"),
    ("the reverse order belongs to the sibling guard", "gh run view 1 --jq .s && sleep 60"),
    # A wait then a gh run subcommand that is NOT view or list. Re-running a failed job on a delay re-fetches nothing, so the twin allows it, and without this case nothing in the corpus could tell the subcommand list
    # from "any gh run at all".
    ("a wait then a rerun is not polling", "sleep 5 && gh run rerun 123"),
]
