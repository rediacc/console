#!/usr/bin/env python3
"""Run `rediacc_ci.quality.review_resolutions` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/review_resolutions.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _gate_args
from _cipath import CI_DIR
from rediacc_ci.quality import review_resolutions

if __name__ == "__main__":
    _gate_args.parse(
        "check_review_resolutions.py", sys.argv[1:], switches=("--selftest",), valued=("--root",)
    )
    raise SystemExit(review_resolutions.main(sys.argv[1:], root=CI_DIR.parent))
