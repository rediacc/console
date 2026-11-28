#!/usr/bin/env python3
"""Run `rediacc_ci.quality.greenlight_closures` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/greenlight_closures.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import greenlight_closures

if __name__ == "__main__":
    _gate_args.parse(
        "check_greenlight_closures.py", sys.argv[1:], switches=("--selftest", "--scan")
    )
    raise SystemExit(greenlight_closures.main(sys.argv[1:]))
