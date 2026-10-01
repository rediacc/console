#!/usr/bin/env python3
"""Entry point for the ported workflow structural gates (`check:ci-workflow-gates`).

The logic lives in `rediacc_ci.security.workflow_gates`; this file exists so the registry can invoke the port BY PATH, as `check_submodule_branches.py` does for its port. `python3 -m` would leave `check:ci-parity` resolving the leaves to `[python3]`.
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.security import workflow_gates

if __name__ == "__main__":
    raise SystemExit(workflow_gates.main(sys.argv[1:]))
