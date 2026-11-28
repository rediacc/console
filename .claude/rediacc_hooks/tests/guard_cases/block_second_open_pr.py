"""The test tables of `block_second_open_pr`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

# `gh` answering is what makes the block direction reachable at all: under the harness default it exits 1 with nothing, which is only the fail-closed arm.
_GH_LIST = (
    '#!/bin/sh\ncat <<\'GHEOF\'\n[{"number":563,"title":"t","headRefName":"b","isDraft":false}]\n'
    "GHEOF\n"
)


_GH_EMPTY = "#!/bin/sh\ncat <<'GHEOF'\n[]\nGHEOF\n"


_GH_DOWN = "#!/bin/sh\necho 'gh: could not connect'\nexit 1\n"


ENVS: list = [
    ("gh-silent-failure", {}, {}),
    ("gh-unreachable", {}, {"gh": _GH_DOWN}),
    ("gh-none-open", {}, {"gh": _GH_EMPTY}),
    ("gh-one-open", {}, {"gh": _GH_LIST}),
]


EDGE_CASES = load_table("block_second_open_pr", "EDGE_CASES")
