"""The test tables of `block_plan_without_depends`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

_ABS = "/nonexistent-plan-deps-probe/agent/plans"


EDGE_CASES = load_table("block_plan_without_depends", "EDGE_CASES")
