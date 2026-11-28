#!/usr/bin/env python3
"""Run `rediacc_ci.quality.content_quality` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/content_quality.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import content_quality

if __name__ == "__main__":
    _gate_args.parse(
        "check_content_quality.py", sys.argv[1:], switches=("--selftest",), positional="<file>"
    )
    raise SystemExit(content_quality.main(sys.argv[1:]))
