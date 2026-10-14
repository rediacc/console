#!/usr/bin/env python3
"""Entry point for the dev-stack liveness probe gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.account_probes`, which pytest and the port's own `--selftest` import directly. A path invocation puts nothing on `sys.path`, hence the `_cipath` hop below.

The subject is `rustfs_alive` in `.ci/rediacc_ci/core/account.py`, the Python port of the retired `.ci/lib/account.sh`; the gate refuses (exit 1, "nothing to check") when that module is absent.

---- gate ----
step: Dev-stack liveness probes
needs: none
selftest: true
---- end gate ----
"""

import sys

import _cipath
from rediacc_ci.quality import account_probes

if __name__ == "__main__":
    raise SystemExit(account_probes.main(sys.argv[1:]))
