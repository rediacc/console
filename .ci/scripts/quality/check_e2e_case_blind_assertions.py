#!/usr/bin/env python3
"""Run `rediacc_ci.quality.e2e_case_blind_assertions` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/e2e_case_blind_assertions.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import e2e_case_blind_assertions

if __name__ == "__main__":
    _gate_args.parse("check_e2e_case_blind_assertions.py", sys.argv[1:], switches=())
    sys.exit(e2e_case_blind_assertions.main())
