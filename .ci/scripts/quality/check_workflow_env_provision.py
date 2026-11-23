#!/usr/bin/env python3
"""Run `rediacc_ci.quality.workflow_env_provision` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/workflow_env_provision.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import workflow_env_provision

if __name__ == "__main__":
    _gate_args.parse("check_workflow_env_provision.py", sys.argv[1:], switches=())
    sys.exit(workflow_env_provision.main())
