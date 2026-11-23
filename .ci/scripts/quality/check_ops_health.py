#!/usr/bin/env python3
"""Run `rediacc_ci.quality.ops_health` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/ops_health.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import ops_health

if __name__ == "__main__":
    _gate_args.parse("check_ops_health.py", sys.argv[1:], switches=("-h", "--help"))
    raise SystemExit(ops_health.main(sys.argv[1:]))
