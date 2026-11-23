"""The test tables of `block_user_only_command`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

_C = ".claude/commands/x.md"


_FM = "---\ndescription: x\n%s---\n\nBody.\n"


EDGE_CASES = [
    (
        "a Write adding the key",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/" + _C,
                "content": _FM % "disable-model-invocation: true\n",
            },
        },
    ),
    (
        "a Write with an explicit false",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/.claude/skills/s/SKILL.md",
                "content": _FM % "disable-model-invocation: false\n",
            },
        },
    ),
    (
        "a Write with another spelling",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/" + _C,
                "content": _FM % "Disable_Model_Invocation : 'Yes'\n",
            },
        },
    ),
    (
        "a nested command tree",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/private/account/.claude/commands/t.md",
                "content": _FM % "disableModelInvocation: on\n",
            },
        },
    ),
    (
        "a NotebookEdit naming a command path",
        {
            "tool_name": "NotebookEdit",
            "tool_input": {
                "notebook_path": "/r/" + _C,
                "new_source": _FM % "disable-model-invocation: 1\n",
            },
        },
    ),
    (
        "a Write whose body only mentions the key",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/" + _C,
                "content": _FM % "" + "Never set `disable-model-invocation: true`.\n",
            },
        },
    ),
    (
        "a Write outside the command directories",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/docs/x.md",
                "content": _FM % "disable-model-invocation: true\n",
            },
        },
    ),
    (
        "a Write to a sub-agent definition",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/.claude/agents/x.md",
                "content": _FM % "disable-model-invocation: true\n",
            },
        },
    ),
    (
        "a commented-out key",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/" + _C,
                "content": _FM % "# disable-model-invocation: true\n",
            },
        },
    ),
    (
        "an Edit of the exception list",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/r/.ci/config/model-invocation-exceptions.json",
                "old_string": "[",
                "new_string": "[{}",
            },
        },
    ),
    ("no path", {"tool_name": "Write", "tool_input": {"content": "x"}}),
]
