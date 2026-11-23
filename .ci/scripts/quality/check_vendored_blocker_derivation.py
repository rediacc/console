#!/usr/bin/env python3
"""Run `rediacc_ci.quality.vendored_blocker_derivation` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/vendored_blocker_derivation.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import vendored_blocker_derivation

if __name__ == "__main__":
    _gate_args.parse("check_vendored_blocker_derivation.py", sys.argv[1:], switches=("--selftest",))
    raise SystemExit(vendored_blocker_derivation.main(sys.argv[1:]))
