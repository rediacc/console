"""Ported from `.ci/scripts/deploy/resolve-www-deploy-target.sh`, which W7 P5 batch B5 retired once `.ci/shadow/w7p5a-resolve-www-deploy-target.observations.jsonl` asserted equivalence over five distinct trees.

Picks the deploy-script name / Worker name / domain / sandbox flag for the www Worker and emits them as GitHub Actions step outputs. Pure computation, same shape as `rediacc_ci.deploy.resolve_account_deploy_config`: no network, no subprocess, one file write to `$GITHUB_OUTPUT`.

REWORDED, NOT BYTE-IDENTICAL, same reasoning as that sibling: the bash twin's
`${VAR:?msg}` diagnostic carries a bash line number that is not worth
reproducing. The ledger's `--finding-re` extracts the substance (the four
`key=value` outputs, or the missing-variable name) rather than the exact
wrapper text.
"""

from __future__ import annotations

import os
import sys

SELF = "resolve-www-deploy-target.py"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def main(argv: list[str]) -> int:
    del argv  # no CLI arguments; every input arrives through the environment
    target = _require("TARGET")
    output_path = _require("GITHUB_OUTPUT")

    if target == "stable":
        script = "deploy-www.sh"
        worker = "rediacc-www"
        domain = "www.rediacc.com"
        sandbox = ""
    else:
        script = "deploy-edge.sh"
        worker = "edge-rediacc-www"
        domain = "edge.rediacc.com"
        sandbox = "--sandbox"

    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write(f"script={script}\n")
        fh.write(f"worker={worker}\n")
        fh.write(f"domain={domain}\n")
        fh.write(f"sandbox={sandbox}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
