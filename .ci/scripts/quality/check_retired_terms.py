#!/usr/bin/env python3
"""Run `rediacc_ci.quality.retired_terms` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/retired_terms.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import retired_terms

if __name__ == "__main__":
    _gate_args.parse(
        "check_retired_terms.py",
        sys.argv[1:],
        switches=("--selftest", "--write-baseline"),
        valued=("--root", "--owner", "--config"),
    )
    raise SystemExit(retired_terms.main(sys.argv[1:]))
