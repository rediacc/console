"""The test tables of `block_inline_workflow_run`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

_FAT = "\n".join(
    ["jobs:", "  a:", "    steps:", "      - name: x", "        run: |"]
    + ["          echo %d" % i for i in range(9)]
)


_ANNOTATED = "\n".join(
    ["jobs:", "  a:", "    steps:", "      - name: x", "        run: |"]
    + ["          # step %d" % i for i in range(3)]
    + ["          echo %d" % i for i in range(6)]
)


EDGE_CASES = [
    (
        "nine logic lines in one block",
        {"tool_input": {"file_path": ".github/workflows/ci.yml", "new_string": _FAT}},
    ),
    # The comment skip, and the reason this guard counts LOGIC lines: nine indented lines, six of them logic.
    (
        "comments inside the block are not logic",
        {"tool_input": {"file_path": ".github/workflows/ci.yaml", "new_string": _ANNOTATED}},
    ),
    # The glob's job: a workflow-shaped fragment in a file that is not a workflow is the CI gate's business, not this hook's.
    (
        "the same fragment outside .github/workflows",
        {"tool_input": {"file_path": "docs/example.yml", "new_string": _FAT}},
    ),
    (
        "a short run block",
        {
            "tool_input": {
                "file_path": ".github/workflows/ci.yml",
                "new_string": "      - run: |\n          npm ci\n          npm test\n",
            }
        },
    ),
    (
        "a run: with no block scalar is not a block",
        {
            "tool_input": {
                "file_path": ".github/workflows/ci.yml",
                "new_string": "      - run: npm ci",
            }
        },
    ),
    (
        "an edits array is collected the same way",
        {"tool_input": {"file_path": ".github/workflows/ci.yml", "edits": [{"new_string": _FAT}]}},
    ),
    (
        "an empty fragment",
        {"tool_input": {"file_path": ".github/workflows/ci.yml", "new_string": ""}},
    ),
]
