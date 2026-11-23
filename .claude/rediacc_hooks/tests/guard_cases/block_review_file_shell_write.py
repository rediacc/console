"""The test tables of `block_review_file_shell_write`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

R = "agent/reviews/1231-9/" + "a" * 40 + ".md"


EDGE_CASES = load_table("block_review_file_shell_write", "EDGE_CASES")
