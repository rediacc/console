"""The test tables of `block_suppressions_shell_write`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

_NQ = "# noq" + "a"


_TSI = "@ts-ignor" + "e"


_SC = "# shellcheck disabl" + "e"


EDGE_CASES = load_table("block_suppressions_shell_write", "EDGE_CASES")
