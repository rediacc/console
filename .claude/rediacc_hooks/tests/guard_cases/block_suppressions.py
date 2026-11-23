"""The test tables of `block_suppressions`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

# Fixture tokens, assembled from halves so this file never holds a literal marker.
_TS_IGNORE = "@ts-ignor" + "e"


_ESLINT_DISABLE = "eslint-disabl" + "e"


_NOQA = "# noq" + "a"


_TYPE_IGNORE = "# type: ignor" + "e"


_NOLINT = "//nolin" + "t"


_SHELLCHECK = "# shellcheck disabl" + "e"


EDGE_CASES = [
    (
        "a directive at a comment opener in a code file",
        {"tool_input": {"file_path": "src/a.ts", "new_string": "// %s\nconst x = 1;" % _TS_IGNORE}},
    ),
    (
        "a block comment opener",
        {"tool_input": {"file_path": "src/a.tsx", "new_string": "/* %s */" % _ESLINT_DISABLE}},
    ),
    (
        "a JSX comment opener",
        {"tool_input": {"file_path": "src/a.tsx", "new_string": "{/* %s */}" % _ESLINT_DISABLE}},
    ),
    # The operator's own example, 2026-10-08.
    (
        "a python marker with a code",
        {
            "tool_input": {
                "file_path": "src/a.py",
                "old_string": "setattr(m, 'x', 1)",
                "new_string": "setattr(m, 'x', 1)  %s: B010" % _NOQA,
            }
        },
    ),
    (
        "a python type ignore",
        {
            "tool_input": {
                "file_path": "src/a.py",
                "content": "x = f()  %s[attr-defined]\n" % _TYPE_IGNORE,
            }
        },
    ),
    (
        "a go nolint",
        {"tool_input": {"file_path": "x/a.go", "new_string": "f() %s:errcheck" % _NOLINT}},
    ),
    (
        "a shellcheck directive",
        {"tool_input": {"file_path": "x/a.sh", "new_string": "%s=SC2086\necho $x" % _SHELLCHECK}},
    ),
    # A SECOND code on an existing marker is growth: the count of (noqa, E501) rises from 0 to 1.
    (
        "a second code added to an existing marker",
        {
            "tool_input": {
                "file_path": "src/a.py",
                "old_string": "import x  %s: F401" % _NOQA,
                "new_string": "import x  %s: F401, E501" % _NOQA,
            }
        },
    ),
    # CONTROLS. Keeping, removing and rewording around an existing marker are all allowed.
    (
        "keeping an existing marker through an unrelated edit",
        {
            "tool_input": {
                "file_path": "src/a.py",
                "old_string": "import x  %s: F401\ny = 1" % _NOQA,
                "new_string": "import x  %s: F401\ny = 2" % _NOQA,
            }
        },
    ),
    (
        "keeping an existing TS directive through an unrelated edit",
        {
            "tool_input": {
                "file_path": "src/a.ts",
                "old_string": "// %s\nconst x = 1;" % _TS_IGNORE,
                "new_string": "// %s\nconst x = 2;" % _TS_IGNORE,
            }
        },
    ),
    (
        "removing a marker",
        {
            "tool_input": {
                "file_path": "src/a.py",
                "old_string": "setattr(m, 'x', 1)  %s: B010" % _NOQA,
                "new_string": "m.x = 1",
            }
        },
    ),
    # Narrowing 1: Markdown is not code.
    (
        "the rule written down in a doc",
        {
            "tool_input": {
                "file_path": "docs/style.md",
                "new_string": "Never write %s; fix the type instead." % _TS_IGNORE,
            }
        },
    ),
    # Narrowing 2: prose inside a code comment, and a Python docstring naming the marker.
    (
        "prose in a code file is still prose",
        {
            "tool_input": {
                "file_path": "src/a.ts",
                "new_string": "// Never write %s; fix the type instead." % _TS_IGNORE,
            }
        },
    ),
    (
        "a python docstring that names the marker",
        {
            "tool_input": {
                "file_path": "src/a.py",
                "content": '"""Never write `%s: B010`."""\nx = 1\n' % _NOQA,
            }
        },
    ),
    (
        "the token with no opener at all",
        {"tool_input": {"file_path": "src/a.ts", "new_string": "const s = '%s';" % _TS_IGNORE}},
    ),
    # No file_path at all: a payload naming no file could be anything, so every language is read and defaulting to "not code" would be a hole.
    (
        "no file_path at all still gets checked",
        {"tool_input": {"new_string": "// %s" % _TS_IGNORE}},
    ),
    (
        "a MultiEdit edits array is collected too",
        {
            "tool_input": {
                "file_path": "src/a.ts",
                "edits": [
                    {"old_string": "a", "new_string": "ok"},
                    {"old_string": "b", "new_string": "// %s" % _TS_IGNORE},
                ],
            }
        },
    ),
    (
        "Write uses content rather than new_string",
        {"tool_input": {"file_path": "src/a.js", "content": "// %s\n" % _ESLINT_DISABLE}},
    ),
    (
        "a NotebookEdit new_source is collected too",
        {"tool_input": {"notebook_path": "nb/a.ipynb", "new_source": "x = 1  %s: F401" % _NOQA}},
    ),
    (
        "an ordinary code edit",
        {"tool_input": {"file_path": "src/a.ts", "new_string": "const x = 1;"}},
    ),
    (
        "a non-code file with no directive",
        {"tool_input": {"file_path": "README.md", "new_string": "hello"}},
    ),
    (
        "a coverage pragma is not a lint suppression",
        {"tool_input": {"file_path": "src/a.py", "new_string": "x = 1  # pragma: no cover"}},
    ),
]
