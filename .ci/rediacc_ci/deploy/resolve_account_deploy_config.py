"""Port of `.ci/scripts/deploy/resolve-account-deploy-config.sh`.

Picks the Worker name / domain / sandbox flag for one region of an account deploy and emits them as GitHub Actions step outputs. Pure computation: no network, no subprocess, no filesystem access beyond appending to `$GITHUB_OUTPUT`. See the bash twin for the full WHY; this port changes no behaviour, only the language.

REWORDED ON PURPOSE, NOT BYTE-IDENTICAL: the bash twin's missing-env-var
message is `${VAR:?msg}`, which bash renders as
`<script>: line N: VAR: <script-name>: VAR must be set` -- the line number is an artifact of bash's own diagnostics, not a fact worth reproducing. This port prints `resolve-account-deploy-config.py: VAR must be set` to stderr and exits
1. `scripts/lib/shadow-gate.ts` rule 1 ("a port is allowed to reword; it is not
allowed to change WHICH things it objects to") is what the ledger checks, via
`--finding-re 'must be set|^(region|worker|domain|sandbox)='`, which extracts
the SUBSTANCE both sides agree on (which variable is missing, or which values were resolved) and ignores the bash-diagnostic wrapper around it.

`MATRIX_SECRET_SUFFIX` is read (and required) but not re-emitted, matching the twin's header note: it fed a Stripe-key indirection that collapsed to one key, so the bash file kept reading it without a consumer to avoid re-deriving the caller's env contract.
"""

from __future__ import annotations

import os
import sys

SELF = "resolve-account-deploy-config.py"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"{SELF}: {name} must be set", file=sys.stderr)
        raise SystemExit(1)
    return value


def main(argv: list[str]) -> int:
    del argv  # no CLI arguments; every input arrives through the environment
    target = _require("TARGET")
    region = _require("MATRIX_ID")
    _require("MATRIX_SECRET_SUFFIX")
    output_path = _require("GITHUB_OUTPUT")

    if target == "stable":
        worker = os.environ.get("MATRIX_WORKER_NAME", "")
        domain = os.environ.get("MATRIX_DOMAIN", "")
        sandbox = ""
    else:
        worker = os.environ.get("MATRIX_EDGE_WORKER_NAME", "")
        domain = os.environ.get("MATRIX_EDGE_DOMAIN", "")
        sandbox = "--sandbox"

    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write(f"region={region}\n")
        fh.write(f"worker={worker}\n")
        fh.write(f"domain={domain}\n")
        fh.write(f"sandbox={sandbox}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
