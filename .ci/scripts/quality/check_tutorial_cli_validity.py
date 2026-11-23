#!/usr/bin/env python3
"""Run `rediacc_ci.quality.tutorial_cli_validity` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/tutorial_cli_validity.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import runpy
import sys

import _cipath
import _gate_args

if __name__ == "__main__":
    _gate_args.parse("check_tutorial_cli_validity.py", sys.argv[1:], switches=())
    runpy.run_module(
        "rediacc_ci.quality.tutorial_cli_validity", run_name="__main__", alter_sys=True
    )
