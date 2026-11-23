#!/usr/bin/env python3
"""Run `rediacc_ci.quality.pathspec_scope` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/pathspec_scope.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import runpy
import sys

import _cipath
import _gate_args

if __name__ == "__main__":
    _gate_args.parse("check_pathspec_scope.py", sys.argv[1:], switches=("--selftest",))
    runpy.run_module("rediacc_ci.quality.pathspec_scope", run_name="__main__", alter_sys=True)
