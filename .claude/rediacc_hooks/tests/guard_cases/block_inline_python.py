"""The test tables of `block_inline_python`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

# The two sides of the escape hatch. Both are run over the whole case list, so the override is proved to let a real finding through rather than assumed to.
ENVS = [
    ("default", {}, {}),
    ("override", {"REDIACC_ALLOW_INLINE_PYTHON": "1"}, {}),
]


# The detector's own control case, reused rather than reinvented: two distinct statement-shaped signals at the head of a line inside one quoted region.
_PROGRAM = "const s = `\nimport os\nimport pathlib\n\ndef go():\n    print(os.getcwd())\n`;\n"


EDGE_CASES = [
    (
        "a program in a template literal",
        {"tool_input": {"file_path": "packages/cli/src/a.ts", "new_string": _PROGRAM}},
    ),
    (
        "the same program in a .mjs file",
        {"tool_input": {"file_path": "packages/cli/bundle.mjs", "content": _PROGRAM}},
    ),
    # "Mentions Python" is far too wide, and the detector says so at length. Naming the interpreter is not a finding; shipping a program is.
    (
        "naming the interpreter is not shipping a program",
        {
            "tool_input": {
                "file_path": "packages/cli/src/a.ts",
                "new_string": 'const bin = "python3";',
            }
        },
    ),
    (
        "ordinary TypeScript",
        {"tool_input": {"file_path": "packages/cli/src/a.ts", "new_string": "const x = 1;"}},
    ),
    # A .py file is where the program is SUPPOSED to live, so this guard has nothing to say about it.
    ("the program in a real .py file", {"tool_input": {"file_path": "a.py", "content": _PROGRAM}}),
    # No `""` arm in the `case`, so a payload naming no file leaves early.
    ("no file_path at all", {"tool_input": {"new_string": _PROGRAM}}),
    (
        "an empty fragment in a code file",
        {"tool_input": {"file_path": "packages/cli/src/a.ts", "new_string": ""}},
    ),
    (
        "a MultiEdit edits array is collected too",
        {"tool_input": {"file_path": "packages/cli/src/a.ts", "edits": [{"new_string": _PROGRAM}]}},
    ),
]
