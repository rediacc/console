"""The test tables of `block_premature_ready`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

# `gh` answering is what reaches the enforcement path at all. The suite's own `ready_case` stubs it for exactly this reason, and its comment says why the old "cannot be tested here, it is the network" claim was not a good one: "the command that would have disproved it took one minute to write".
ENVS: list = [
    ("gh-silent-failure", {}, {}),
    ("ci-green", {}, {"gh": "#!/bin/sh\necho SUCCESS\n"}),
    ("ci-red", {}, {"gh": "#!/bin/sh\necho FAILURE\n"}),
]


EDGE_CASES = load_table("block_premature_ready", "EDGE_CASES")
