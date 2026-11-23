"""The test tables of `block_review_file_edit`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    (
        "a Write over a review file",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/agent/reviews/1231-9/%s.md" % ("a" * 40),
                "content": "x",
            },
        },
    ),
    (
        "an Edit of a review file",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "agent/reviews/1231-9/x.md",
                "old_string": "[high]",
                "new_string": "[low]",
            },
        },
    ),
    (
        "an Edit of the clean ledger",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "agent/reviews/1231-9/clean.jsonl",
                "old_string": "x",
                "new_string": "y",
            },
        },
    ),
    (
        "a MultiEdit of a review file",
        {
            "tool_name": "MultiEdit",
            "tool_input": {"file_path": "agent/reviews/b/x.md", "edits": []},
        },
    ),
    (
        "a NotebookEdit naming a review path",
        {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "agent/reviews/b/x.md"}},
    ),
    (
        "a plan that mentions the directory",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "agent/plans/PLAN-x.md", "content": "agent/reviews/"},
        },
    ),
    (
        "a sibling directory with a similar name",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "agent/reviews-old/x.md", "content": "x"},
        },
    ),
    (
        "a file called reviews elsewhere",
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": "docs/agent/reviewsx.md", "new_string": "x"},
        },
    ),
    ("no path", {"tool_name": "Write", "tool_input": {"content": "x"}}),
]
