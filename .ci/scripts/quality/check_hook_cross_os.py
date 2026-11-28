#!/usr/bin/env python3
"""Run `rediacc_ci.quality.hook_cross_os` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/hook_cross_os.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import hook_cross_os

if __name__ == "__main__":
    _gate_args.parse(
        "check_hook_cross_os.py",
        sys.argv[1:],
        switches=("--selftest",),
        valued=("--root",),
        equals=("--root",),
    )
    raise SystemExit(hook_cross_os.main(sys.argv[1:]))
