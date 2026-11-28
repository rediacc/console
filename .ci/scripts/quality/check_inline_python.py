#!/usr/bin/env python3
"""Run `rediacc_ci.quality.inline_python` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/inline_python.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
from rediacc_ci.quality import inline_python

if __name__ == "__main__":
    sys.exit(inline_python.main())
