#!/usr/bin/env python3
"""Run `rediacc_ci.quality.lint_rule_liveness` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/lint_rule_liveness.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
from rediacc_ci.quality import lint_rule_liveness

if __name__ == "__main__":
    sys.exit(lint_rule_liveness.main())
