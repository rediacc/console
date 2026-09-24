#!/usr/bin/env python3
"""Entry point for the bash-lib port completeness gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.bash_lib_migration_complete`, which the gate's own `--selftest` exercises.

---- gate ----
step: Bash-lib port completeness
needs: none
lane: quality-static
selftest: true
why: account.sh reached 22 of 22 ported functions on 2026-09-24 by a hand count;
     nothing stopped a new bash function or a renamed Python def from reopening the gap
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import bash_lib_migration_complete

if __name__ == "__main__":
    raise SystemExit(bash_lib_migration_complete.main(sys.argv[1:]))
