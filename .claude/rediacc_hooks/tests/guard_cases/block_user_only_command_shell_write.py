"""The test tables of `block_user_only_command_shell_write`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

_K = "disable-model-invocation"


_C = ".claude/commands/x.md"


EDGE_CASES = load_table("block_user_only_command_shell_write", "EDGE_CASES")
