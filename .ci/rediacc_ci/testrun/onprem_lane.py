"""The on-premise CI lane (PLAN-rmcp-executor-hardening.md, Design 17, box EHOP3).

    npm run test:onprem [-- <onprem_scenarios arguments>]

Brings the on-premise stack up with a container machine, runs the scenario runner (every registered suite unless the arguments name `--suite`, `--all` or `--list`), and takes the stack down again whatever the run did. The lane's exit code is the runner's, or the teardown's when the runner passed and `down` did not, so a stack left running never reads as green.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from rediacc_ci import log
from rediacc_ci.testrun import onprem_scenarios, onprem_stack

SELF = "rediacc_ci.testrun.onprem_lane"
Runner = Callable[[list[str]], int]


def main(
    argv: list[str],
    stack: Runner = onprem_stack.main,
    scenarios: Runner = onprem_scenarios.main,
) -> int:
    up = stack(["up", "--machines", "container"])
    if up != 0:
        # `up` undoes every start it recorded before it fails, so there is nothing to take down.
        log.error(f"{SELF}: the stack did not come up (rc {up})")
        return up
    try:
        ran = scenarios(argv or ["--all"])
    finally:
        down = stack(["down"])
    if ran == 0 and down != 0:
        log.error(f"{SELF}: the scenarios passed but `down` failed (rc {down})")
        return down
    return ran


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
