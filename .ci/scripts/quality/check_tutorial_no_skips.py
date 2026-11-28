#!/usr/bin/env python3
"""Run `rediacc_ci.quality.tutorial_no_skips` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/tutorial_no_skips.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import tutorial_no_skips

if __name__ == "__main__":
    _gate_args.parse("check_tutorial_no_skips.py", sys.argv[1:], switches=())
    sys.exit(tutorial_no_skips.main())
