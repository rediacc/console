#!/usr/bin/env python3
"""Run `rediacc_ci.quality.pr_head_ref_completeness` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/pr_head_ref_completeness.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import pr_head_ref_completeness

if __name__ == "__main__":
    _gate_args.parse("check_pr_head_ref_completeness.py", sys.argv[1:], switches=())
    sys.exit(pr_head_ref_completeness.main())
