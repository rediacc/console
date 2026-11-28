#!/usr/bin/env python3
"""Run `rediacc_ci.quality.scope_completeness` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/scope_completeness.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
from rediacc_ci.quality import scope_completeness

if __name__ == "__main__":
    sys.exit(scope_completeness.main())
