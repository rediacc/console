#!/usr/bin/env python3
"""Run `rediacc_ci.quality.generated_artifacts` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/generated_artifacts.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import generated_artifacts

if __name__ == "__main__":
    _gate_args.parse("check_generated_artifacts.py", sys.argv[1:], switches=("--selftest",))
    sys.exit(generated_artifacts.main(sys.argv[1:]))
