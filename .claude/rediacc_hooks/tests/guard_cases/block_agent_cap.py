"""The test tables of `block_agent_cap`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

# The payload shapes the differential feeds this guard beyond the cross-fed corpus. A session id that resolves to no session directory is the "cannot count" branch; the Explore spawn is the read-only exemption.
EDGE_CASES = [
    (
        "writer-spawn-uncountable",
        {
            "tool_name": "Agent",
            "session_id": "zz-no-such-session",
            "cwd": "/nonexistent-agent-cap-fixture",
            "tool_input": {"subagent_type": "general-purpose", "description": "x"},
        },
    ),
    (
        "reader-spawn",
        {
            "tool_name": "Agent",
            "session_id": "zz-no-such-session",
            "cwd": "/nonexistent-agent-cap-fixture",
            "tool_input": {"subagent_type": "Explore", "description": "x"},
        },
    ),
]
