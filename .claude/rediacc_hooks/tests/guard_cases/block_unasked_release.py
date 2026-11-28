"""The test tables of `block_unasked_release`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

_ASK = "ASKED:2026-01-01T00:00Z"


_PY = "PYTHONPATH=.ci python3 -m"


EDGE_CASES = load_table("block_unasked_release", "EDGE_CASES")
