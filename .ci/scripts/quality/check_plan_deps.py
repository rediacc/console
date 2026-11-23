#!/usr/bin/env python3
"""Run `rediacc_ci.quality.plan_deps` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/plan_deps.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import plan_deps

if __name__ == "__main__":
    _gate_args.parse(
        "check_plan_deps.py",
        sys.argv[1:],
        switches=(
            "--selftest",
            "--overlaps",
            "--migrate-x",
            "--table",
            "--save",
            "--diff",
            "--write",
            "--draft",
            "--set",
            "--set-x",
        ),
        valued=("--apply", "--root", "--base-tree"),
        positional="<path> <value>...",
    )
    sys.exit(plan_deps.main(sys.argv[1:]))
