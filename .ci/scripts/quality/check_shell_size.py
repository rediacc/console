#!/usr/bin/env python3
"""Run `rediacc_ci.quality.shell_size` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/shell_size.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import shell_size

if __name__ == "__main__":
    _gate_args.parse("check_shell_size.py", sys.argv[1:], switches=("--selftest",))
    raise SystemExit(shell_size.main(sys.argv[1:]))
