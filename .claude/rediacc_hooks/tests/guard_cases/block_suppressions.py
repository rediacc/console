"""The test tables of `block_suppressions`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

# Fixture tokens, assembled from halves so this file never holds a literal marker.
_TS_IGNORE = "@ts-ignor" + "e"


_ESLINT_DISABLE = "eslint-disabl" + "e"


_NOQA = "# noq" + "a"


_TYPE_IGNORE = "# type: ignor" + "e"


_NOLINT = "//nolin" + "t"


_SHELLCHECK = "# shellcheck disabl" + "e"


EDGE_CASES = load_table("block_suppressions", "EDGE_CASES")
