"""The test tables of `block_agent_cap`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

# The payload shapes the differential feeds this guard beyond the cross-fed corpus. A session id that resolves to no session directory is the "cannot count" branch; the Explore spawn is the read-only exemption.
EDGE_CASES = load_table("block_agent_cap", "EDGE_CASES")
