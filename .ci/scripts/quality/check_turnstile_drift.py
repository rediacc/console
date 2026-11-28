#!/usr/bin/env python3
"""Run `rediacc_ci.quality.turnstile_drift` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/turnstile_drift.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import turnstile_drift

if __name__ == "__main__":
    _gate_args.parse("check_turnstile_drift.py", sys.argv[1:], switches=("--selftest",))
    raise SystemExit(turnstile_drift.main(sys.argv[1:]))
