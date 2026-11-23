#!/usr/bin/env python3
"""Run `rediacc_ci.quality.probe_parity` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/probe_parity.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import probe_parity

if __name__ == "__main__":
    _gate_args.parse("check_probe_parity.py", sys.argv[1:], switches=("--selftest",))
    raise SystemExit(probe_parity.main(sys.argv[1:]))
