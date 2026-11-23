"""The test tables of `block_ci_reverse_poll`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    (
        "the pinned prose ruling: a heredoc still fires",
        "cat <<EOF\ngh run view 1 --jq .x && sleep 30\nEOF",
    ),
    (
        "quoted prose still fires, by the same ruling",
        "echo 'gh run view 1 --jq .status && sleep 30'",
    ),
    ("a plain run view is not polling", "gh run view 123 --json status"),
    ("--jq with no wait after it", "gh run view 123 --jq .status"),
    ("a separator between them is not the && shape", "gh run view 1 --jq .s; sleep 30"),
    # The case the planted defect needs, and it is a real shape rather than a test-shaped one: reading a run and then doing something that is not a wait. Without it nothing in the whole corpus could tell the pattern with its `sleep` tail from the pattern without it, and the anti-vacuity control said so on the first run rather than at review time.
    ("--jq then a command that is not a wait", "gh run view 1 --jq .status && echo done"),
]
