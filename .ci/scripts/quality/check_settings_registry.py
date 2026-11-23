#!/usr/bin/env python3
"""Run `rediacc_ci.quality.settings_registry` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/settings_registry.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
from rediacc_ci.quality import settings_registry

if __name__ == "__main__":
    sys.exit(settings_registry.main(sys.argv[1:]))
