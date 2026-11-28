#!/usr/bin/env python3
"""Run `rediacc_ci.quality.scope_mirrors` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/scope_mirrors.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

from _cipath import CI_DIR
from rediacc_ci.quality import scope_mirrors

if __name__ == "__main__":
    raise SystemExit(scope_mirrors.main(sys.argv[1:], root=CI_DIR.parent))
