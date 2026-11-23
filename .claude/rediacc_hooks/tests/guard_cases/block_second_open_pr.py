"""The test tables of `block_second_open_pr`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.wellknown import RENET_REPO

# `gh` answering is what makes the block direction reachable at all: under the harness default it exits 1 with nothing, which is only the fail-closed arm.
_GH_LIST = (
    '#!/bin/sh\ncat <<\'GHEOF\'\n[{"number":563,"title":"t","headRefName":"b","isDraft":false}]\n'
    "GHEOF\n"
)


_GH_EMPTY = "#!/bin/sh\ncat <<'GHEOF'\n[]\nGHEOF\n"


_GH_DOWN = "#!/bin/sh\necho 'gh: could not connect'\nexit 1\n"


ENVS = [
    ("gh-silent-failure", {}, {}),
    ("gh-unreachable", {}, {"gh": _GH_DOWN}),
    ("gh-none-open", {}, {"gh": _GH_EMPTY}),
    ("gh-one-open", {}, {"gh": _GH_LIST}),
]


EDGE_CASES = [
    ("the create this guard exists for", "gh pr create --draft -t x -b y"),
    ("sh -c wrapping does not bypass it", "sh -c 'gh pr create --draft -t x -b y'"),
    # THE CONTROL THAT MATTERS: with no open PR the guard must be invisible, or it would block the FIRST PR too and simply stop all work.
    ("a non-create gh command is ignored", "gh pr view 567"),
    (
        "a submodule create is judged against ITS repo",
        ("gh pr create --repo " + RENET_REPO + " -t x"),
    ),
    ("prose naming the command", "echo 'gh pr create --draft'"),
]
