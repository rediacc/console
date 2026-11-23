"""The test tables of `block_agent_state_shape`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

EDGE_CASES = [
    # Judged where the write LANDS (#bc7d998c): each refusal was allowed before, and the control was refused.
    (
        "a .. detour into a session's STATE.md",
        {"tool_input": {"file_path": "agent/x/../d1589e0b/STATE.md"}},
    ),
    (
        "a docs/agent prefix that lands in agent/",
        {"tool_input": {"file_path": "docs/agent/../../agent/d1589e0b/STATE.md"}},
    ),
    (
        "a .. detour that lands in docs/agent",
        {"tool_input": {"file_path": "agent/d1589e0b/../../docs/agent/x/STATE.md"}},
    ),
    # The live shape as of 2026-08-18: one component below `agent`.
    ("the live one-component shape", {"tool_input": {"file_path": "agent/d1589e0b/STATE.md"}}),
    ("the same path with a leading ./", {"tool_input": {"file_path": "./agent/d1589e0b/STATE.md"}}),
    # Both retired shapes, kept deliberately.
    (
        "the retired two-component shape",
        {"tool_input": {"file_path": "agent/0831-1/d1589e0b/STATE.md"}},
    ),
    ("the legacy dotted tree", {"tool_input": {"file_path": ".agent/0831-1/STATE.md"}}),
    # The named residual: a submodule's own agent/ tree is guarded too, and so is an unrelated tree that happens to have one.
    (
        "a submodule's agent tree",
        {"tool_input": {"file_path": "private/renet/agent/d1589e0b/STATE.md"}},
    ),
    # The docs trees, excluded outright.
    ("docs/agent is standing prose", {"tool_input": {"file_path": "docs/agent/x/STATE.md"}}),
    (
        "docs/agent-reference is standing prose",
        {"tool_input": {"file_path": "docs/agent-reference/x/STATE.md"}},
    ),
    # Segment awareness: `agent` must START a path component.
    ("a component merely ending in agent", {"tool_input": {"file_path": "myagent/x/STATE.md"}}),
    # Three components below `agent` is neither live nor retired.
    (
        "three components below agent",
        {"tool_input": {"file_path": "agent/a/b/c/STATE.md"}},
    ),
    (
        "RULES.md is deliberately untouched",
        {"tool_input": {"file_path": "agent/d1589e0b/RULES.md"}},
    ),
    # `notebook_path` is the second source the jq alternation reads.
    ("a NotebookEdit names notebook_path", {"tool_input": {"notebook_path": "agent/x/STATE.md"}}),
    ("no path at all", {"tool_input": {"new_string": "hello"}}),
]
