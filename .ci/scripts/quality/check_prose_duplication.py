#!/usr/bin/env python3
"""Entry point for the PR-loop prose-duplication gate. Logic is in `rediacc_ci.quality.prose_duplication`.

The family, the unit, the excluded text, the threshold and the blind spots are documented on the module; agent/plans/PLAN-pr-loop-single-source.md D6 is the design. This file exists so the registry can invoke the gate BY PATH, and the `---- gate ----` header is here because `gate-bind` reads the file package.json names.

Flags: `--selftest`, `--root <dir>` (the gate test runs the entry point against a copied tree).

---- gate ----
step: PR loop docs carry no duplicated passage
needs: none
lane: quality-content
selftest: true
why: CLAUDE.md, /pr-babysit, the pr-babysitter agent and /pr-merge are what an agent
     reads to drive the PR loop, and a passage copied between two of them drifts when
     only one is edited. Each rule keeps one home and the other files point at it; a
     shared run of 25 or more normalized words outside code, gen-docs regions and
     registered scope spans is red.
---- end gate ----
"""

import sys

import _gate_args
from _cipath import CI_DIR
from rediacc_ci.quality import prose_duplication

if __name__ == "__main__":
    _gate_args.parse(
        "check_prose_duplication.py", sys.argv[1:], switches=("--selftest",), valued=("--root",)
    )
    raise SystemExit(prose_duplication.main(sys.argv[1:], root=CI_DIR.parent))
