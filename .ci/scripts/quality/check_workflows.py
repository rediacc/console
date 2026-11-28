#!/usr/bin/env python3
"""Run `rediacc_ci.quality.workflows` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/workflows.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import workflows

if __name__ == "__main__":
    _gate_args.parse(
        "check_workflows.py", sys.argv[1:], switches=("--selftest", "--refresh-retention")
    )
    raise SystemExit(workflows.main(sys.argv[1:]))
