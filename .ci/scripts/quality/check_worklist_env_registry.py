#!/usr/bin/env python3
"""Run `rediacc_ci.quality.worklist_env_registry` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/worklist_env_registry.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import worklist_env_registry

if __name__ == "__main__":
    _gate_args.parse("check_worklist_env_registry.py", sys.argv[1:], switches=("--selftest",))
    raise SystemExit(worklist_env_registry.main(sys.argv[1:]))
