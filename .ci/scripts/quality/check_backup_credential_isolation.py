#!/usr/bin/env python3
"""Entry point for the backup credential isolation gate.

The logic, the six rules and the controls live in `rediacc_ci.quality.backup_credential_isolation`; this file exists so the registry can invoke it BY PATH, the same split `check_retired_terms.py` uses. The `---- gate ----` header is HERE and not on the module, because `gate-bind` reads the file package.json names.

---- gate ----
step: Backup credential isolation
lane: quality-security
needs: submodules
why: one account-wide R2 key once reached the public bench Worker through a
     fallback in deploy_bench, and one shared backup pair served every
     environment. Each environment now holds only its own bucket-scoped pair;
     this pins the profiles, the deploy workflow and the rotation scopes to that
     split, by name, so an edit cannot quietly re-widen it.
---- end gate ----
"""

import sys

import _cipath
from rediacc_ci.quality import backup_credential_isolation

if __name__ == "__main__":
    raise SystemExit(backup_credential_isolation.main(sys.argv[1:]))
