"""The test tables of `block_short_wake_timeout`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    (
        "the 2026-11-10 incident: backgrounded with & after nothing else",
        {
            "tool_input": {
                "command": "python3 .claude/hooks/stop/wl_wake.py d778be9d --minutes 30 >/dev/null 2>&1 & true",
                "run_in_background": False,
            }
        },
    ),
    (
        "chained after another command in a background task",
        {
            "tool_input": {
                "command": "npm test; python3 .claude/hooks/stop/wl_wake.py d778be9d",
                "run_in_background": True,
                "timeout": 2400000,
            }
        },
    ),
    (
        "the right shape with the harness default timeout",
        {
            "tool_input": {
                "command": "python3 .claude/hooks/stop/wl_wake.py d778be9d",
                "run_in_background": True,
            }
        },
    ),
    (
        "the right shape in the foreground",
        {
            "tool_input": {
                "command": "python3 .claude/hooks/stop/wl_wake.py d778be9d",
                "timeout": 2400000,
            }
        },
    ),
    (
        "the correct arm",
        {
            "tool_input": {
                "command": "python3 .claude/hooks/stop/wl_wake.py d778be9d",
                "run_in_background": True,
                "timeout": 2400000,
            }
        },
    ),
    (
        "a heredoc read by cat that names the timer",
        "cat <<'E'\npython3 .claude/hooks/stop/wl_wake.py d778be9d &\nE",
    ),
    ("a grep naming the timer", "grep -n wl_wake.py .claude/hooks/stop/wl_checks.py"),
    ("the usage line", "python3 .claude/hooks/stop/wl_wake.py --help"),
]
