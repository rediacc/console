"""The test tables of `block_unscoped_formatter_run`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

INCIDENT = (
    "R=ruff; $R format $( $R format --check a.py b.py 2>&1 | grep 'Would reformat'"
    " | sed 's/Would reformat: //')"
)


EDGE_CASES = load_table("block_unscoped_formatter_run", "EDGE_CASES")
