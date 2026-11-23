"""The test tables of `block_long_sleep`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    ("a foreground sleep over the cap", "sleep 45"),
    ("a foreground sleep at the cap is allowed", "sleep 20"),
    # Correction 1: the largest wins, not the first.
    ("the maximum wins, not the first", "sleep 20; sleep 90"),
    # Correction 2: the background cap is higher, which is what makes the attempt-stable watch expressible at all.
    (
        "the same command in the background is under the higher cap",
        {"tool_input": {"command": "sleep 20; sleep 90", "run_in_background": True}},
    ),
    (
        "a background sleep over the background cap",
        {"tool_input": {"command": "sleep 300", "run_in_background": True}},
    ),
    # A leading zero is decimal: twenty-four seconds, as `sleep` reads it.
    ("a leading zero is decimal, as sleep reads it", "sleep 024"),
    ("no sleep at all", "gh run view 123"),
    # A tab separates words for bash, so since the command-position reading this IS a 45-second sleep.
    ("a tab between sleep and its argument is a sleep", "sleep\t45"),
    # #8e5a6452: the word inside a quoted argument is prose, not a command.
    ("quoted prose naming a sleep", "printf '%s\\n' 'which sleep 600 s (a full run)' > msg.txt"),
    ("a minute suffix", "sleep 1m"),
    ("a heredoc body is still scanned", "git commit -F - <<'M'\nwhich sleep 600 s\nM"),
    # #503f0ba8: a command `npx` or `find -exec` LAUNCHES is judged as a run of its own.
    ("a sleep launched by find -exec", r"find . -maxdepth 0 -exec sleep 900 \;"),
    ("a sleep launched by npx", "npx sleep 900"),
    ("prose naming a launched sleep", "echo find . -maxdepth 0 -exec sleep 900"),
]
