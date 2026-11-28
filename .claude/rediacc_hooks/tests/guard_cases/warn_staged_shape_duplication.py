"""The test tables of `warn_staged_shape_duplication`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

EDGE_CASES = load_table("warn_staged_shape_duplication", "EDGE_CASES")
