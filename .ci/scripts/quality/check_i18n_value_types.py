#!/usr/bin/env python3
"""Run `rediacc_ci.quality.i18n_value_types` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/i18n_value_types.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
from rediacc_ci.quality import i18n_value_types

if __name__ == "__main__":
    sys.exit(i18n_value_types.main())
