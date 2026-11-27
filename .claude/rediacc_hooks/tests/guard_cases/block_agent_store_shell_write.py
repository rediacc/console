"""The test tables of `block_agent_store_shell_write`, kept out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`. The full `(name, command, refused?)` set is `SHELL_CASES` in the same fixture file, run by `test-block_agent_store_shell_write.py`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

EDGE_CASES = load_table("block_agent_store_shell_write", "EDGE_CASES")
