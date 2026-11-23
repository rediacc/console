"""The test tables of `block_origin_clone`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

from rediacc_hooks import wellknown
from rediacc_hooks.guards.block_origin_clone import githooks

_GHO = wellknown.GH_ORIGIN


_CONSOLE = wellknown.GH_REPO


_RENET = wellknown.RENET_REPO


_MIRROR = githooks.MIRROR_HOST


EDGE_CASES = [
    ("the origin", f"git clone {_GHO}/{_CONSOLE}.git /tmp/x"),
    ("a submodule", f"git clone git@github.com:{_RENET}.git /tmp/x"),
    ("the mirror", f"git clone https://{_MIRROR}/rediacc-org/github/console.git /tmp/x"),
    ("gh", f"gh repo clone {_CONSOLE}"),
    ("a wrapper", f"sh -c 'git clone {_GHO}/{_CONSOLE} /tmp/x'"),
    (
        "init and fetch",
        f"git init /tmp/x && git -C /tmp/x fetch {_GHO}/{_CONSOLE}.git",
    ),
    (
        "program text",
        f"python3 -c \"import os; os.system('git clone {_GHO}/{_CONSOLE} /x')\"",
    ),
    ("control: a fixture", "git clone /tmp/fixture /tmp/y"),
    ("control: an unrelated url", "git clone https://example.invalid/a.git /tmp/y"),
    ("control: prose", f"echo git clone {_GHO}/{_CONSOLE}.git /tmp/x"),
    (
        "control: a heredoc body",
        f"cat > n.md <<'EOF'\ngit clone {_GHO}/{_CONSOLE}.git /tmp/x\nEOF",
    ),
]
