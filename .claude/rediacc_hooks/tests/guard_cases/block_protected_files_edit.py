"""The test tables of `block_protected_files_edit`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

# The cases that need no world on disk; the restore cases need a checkout and live in the harness.
EDGE_CASES = [
    (
        "a Write emptying the settings file",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "/r/.claude/settings.json", "content": ""},
        },
    ),
    (
        "a Write blanking the pre-commit script",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "/r/scripts/pre-commit-check.sh", "content": "\n \n"},
        },
    ),
    (
        "a NotebookEdit naming the settings file",
        {
            "tool_name": "NotebookEdit",
            "tool_input": {"notebook_path": "/r/.claude/settings.json", "new_source": "x"},
        },
    ),
    (
        "a Write of new settings text",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "/r/.claude/settings.json", "content": '{"hooks": {}}\n'},
        },
    ),
    (
        "a Write emptying an ordinary file",
        {"tool_name": "Write", "tool_input": {"file_path": "/r/docs/x.md", "content": ""}},
    ),
    (
        "a Write emptying the local settings file",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "/r/.claude/settings.local.json", "content": ""},
        },
    ),
    ("no path", {"tool_name": "Write", "tool_input": {"content": ""}}),
]
