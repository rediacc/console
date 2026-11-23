"""The test tables of `block_inline_workflow_run`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

_FAT = "\n".join(
    ["jobs:", "  a:", "    steps:", "      - name: x", "        run: |"]
    + ["          echo %d" % i for i in range(9)]
)


_ANNOTATED = "\n".join(
    ["jobs:", "  a:", "    steps:", "      - name: x", "        run: |"]
    + ["          # step %d" % i for i in range(3)]
    + ["          echo %d" % i for i in range(6)]
)


EDGE_CASES = load_table("block_inline_workflow_run", "EDGE_CASES")
