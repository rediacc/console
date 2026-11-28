"""The test tables of `block_host_toolchain_run`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

# The three docker worlds this guard's tail distinguishes, driven rather than described. Without them the differential only ever sees whichever devbox this machine happens to be running, and the two NOTE branches plus the refusal are a coin toss decided by another session's `devbox up`.
ENVS: list = [
    ("no-devbox", {}, {"docker": "#!/bin/sh\nexit 0\n"}),
    (
        "devbox-without-tool",
        {},
        {"docker": '#!/bin/sh\ncase "$1" in ps) echo rediacc-devbox-x ;; exec) exit 1 ;; esac\n'},
    ),
    (
        "devbox-with-tool",
        {},
        {"docker": '#!/bin/sh\ncase "$1" in ps) echo rediacc-devbox-x ;; exec) exit 0 ;; esac\n'},
    ),
]


EDGE_CASES = load_table("block_host_toolchain_run", "EDGE_CASES")
