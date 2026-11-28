#!/usr/bin/env python3
"""Run `rediacc_ci.quality.aws_resolver` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/aws_resolver.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import aws_resolver

if __name__ == "__main__":
    _gate_args.parse(
        "check_aws_resolver.py", sys.argv[1:], switches=("--selftest",), valued=("--root",)
    )
    raise SystemExit(aws_resolver.main(sys.argv[1:]))
