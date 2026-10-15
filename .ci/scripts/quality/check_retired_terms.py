#!/usr/bin/env python3
"""Entry point for the retired-terms gate.

The logic, the refuse-or-advise split and the controls live in `rediacc_ci.quality.retired_terms`; this file exists so the registry can invoke it BY PATH, the same split `check_account_env_retired.py` uses. The `---- gate ----` header is HERE and not on the module, because `gate-bind` reads the file package.json names.

---- gate ----
step: Retired terms
lane: quality-static
needs: none
why: a retirement does not reach the work already queued against it. Worklist item
     #fcd7316f stayed open to bake rclone into an image after rclone was ordered
     removed, so an open item or a live plan naming a retired term is reported
     unless it cites the work doing the retiring.
---- end gate ----
"""

import sys

import _cipath
from rediacc_ci.quality import retired_terms

if __name__ == "__main__":
    raise SystemExit(retired_terms.main(sys.argv[1:]))
