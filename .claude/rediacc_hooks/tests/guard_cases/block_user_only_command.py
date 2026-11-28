"""The test tables of `block_user_only_command`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

_C = ".claude/commands/x.md"


_FM = "---\ndescription: x\n%s---\n\nBody.\n"


EDGE_CASES = load_table("block_user_only_command", "EDGE_CASES")
