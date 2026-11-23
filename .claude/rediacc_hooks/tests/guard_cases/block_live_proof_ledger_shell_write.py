"""The test tables of `block_live_proof_ledger_shell_write`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.guards import block_live_proof_ledger_write as EDIT
from rediacc_hooks.tests.fixtures.guards.loader import load_table

LEDGER_REL = EDIT.LEDGER_REL


EDGE_CASES = load_table("block_live_proof_ledger_shell_write", "EDGE_CASES")
