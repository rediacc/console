#!/usr/bin/env python3
"""Run `rediacc_ci.quality.gh_retry_gate` by path.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/gh_retry_gate.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import gh_retry_gate

if __name__ == "__main__":
    _gate_args.parse(
        "check_gh_retry_reads.py",
        sys.argv[1:],
        switches=("--selftest", "--quiet-writes", "--init-baseline"),
        valued=("--root", "--shell-root", "--write-baseline"),
    )
    raise SystemExit(gh_retry_gate.main(sys.argv[1:]))
