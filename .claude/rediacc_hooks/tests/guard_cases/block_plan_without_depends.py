"""The test tables of `block_plan_without_depends`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

_ABS = "/nonexistent-plan-deps-probe/agent/plans"


EDGE_CASES = [
    # The refusals, on a new plan in this tree.
    (
        "a new live plan without the field",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\n",
            },
        },
    ),
    (
        "a malformed value (a path token)",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: agent/plans/PLAN-x.md\n",
            },
        },
    ),
    (
        "a dangling token",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: PLAN-zz-nowhere.md\n",
            },
        },
    ),
    (
        "a self-dependency",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: PLAN-zz-probe.md\n",
            },
        },
    ),
    (
        "no-dep with a placeholder reason",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: no-dep -- n/a\n",
            },
        },
    ),
    # The allows: the same plan, fixed; and everything out of scope or exempt.
    (
        "no-dep with a reason",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: no-dep -- a probe plan with no upstream work\n",
            },
        },
    ),
    (
        "a stub",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-zz-probe.md\n",
            },
        },
    ),
    (
        "a finished record",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: compacted\n",
            },
        },
    ),
    (
        "a _done/ path",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/_done/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\n",
            },
        },
    ),
    (
        "a harness plan",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".claude/plans/zz-probe.md",
                "content": "# P\n\nStatus: draft\n",
            },
        },
    ),
    (
        "a non-plan doc",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "docs/zz-probe.md", "content": "Status: draft\n"},
        },
    ),
    (
        "an Edit to a plan that does not exist (the tool itself fails)",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "%s/PLAN-zz-probe.md" % _ABS,
                "old_string": "a",
                "new_string": "b",
            },
        },
    ),
    ("no file path at all", {"tool_name": "Write", "tool_input": {"content": "Status: draft\n"}}),
    # The X fields and the operator freeze.
    (
        "a malformed Priority",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: no-dep -- a probe plan with no upstream work\nPriority: P7\n",
            },
        },
    ),
    (
        "the AI introducing an operator Priority with no operator turn",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: no-dep -- a probe plan with no upstream work\nPriority: P1 (operator)\n",
            },
        },
    ),
    (
        "an AI Priority",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "agent/plans/PLAN-zz-probe.md",
                "content": "# P\n\nStatus: draft\nDepends-On: no-dep -- a probe plan with no upstream work\nPriority: P1 -- proposed by AI\nConcurrency: parallel\nOwns: docs/zz-probe.md\n",
            },
        },
    ),
]
