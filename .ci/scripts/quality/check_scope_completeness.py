#!/usr/bin/env python3
"""Run `rediacc_ci.quality.scope_completeness` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/scope_completeness.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import runpy

import _cipath

if __name__ == "__main__":
    runpy.run_module("rediacc_ci.quality.scope_completeness", run_name="__main__", alter_sys=True)
