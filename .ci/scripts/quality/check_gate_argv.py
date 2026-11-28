#!/usr/bin/env python3
"""Entry point for check:ci-gate-argv: every quality entry point refuses an argument it does not take.

The logic lives in `rediacc_ci.quality.gate_argv` (PLAN-silent-failure-sweep.md SF8, design D4). This file uses the shared parser itself, so the gate that polices `_gate_args.parse` is one of the entry points it counts.

---- gate ----
step: Gate argv
needs: none
selftest: true
lane: quality-static
why: `npm run check:ci-record-paths -- --update` exited 0 having done nothing, because the
     entry point only asked about the flags it knew. SF1 put the shared parser into every
     quality entry point; this gate keeps it there, refuses a hand scan or a dropped argv,
     and checks every registered call's flags against the declared set.
---- end gate ----
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import gate_argv

if __name__ == "__main__":
    _gate_args.parse("check_gate_argv.py", sys.argv[1:], switches=("--selftest",))
    raise SystemExit(gate_argv.main(sys.argv[1:]))
