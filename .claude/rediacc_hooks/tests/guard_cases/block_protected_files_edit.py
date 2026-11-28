"""The test tables of `block_protected_files_edit`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

# The cases that need no world on disk; the restore cases need a checkout and live in the harness.
EDGE_CASES = load_table("block_protected_files_edit", "EDGE_CASES")
