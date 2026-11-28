"""The test tables of `block_origin_clone`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks import wellknown
from rediacc_hooks.guards.block_origin_clone import githooks
from rediacc_hooks.tests.fixtures.guards.loader import load_table

_GHO = wellknown.GH_ORIGIN


_CONSOLE = wellknown.GH_REPO


_RENET = wellknown.RENET_REPO


_MIRROR = githooks.MIRROR_HOST


EDGE_CASES = load_table("block_origin_clone", "EDGE_CASES")
