#!/usr/bin/env python3
"""Entry point for check:ci-model-invocable-commands: no tracked slash command or skill disables model invocation, except a file on the operator's exception list.

Operator ruling 2026-10-09: "no command or skill in this repo is user-only. Every slash command and skill must be invocable by the AI. This is enforced twice: a hook refuses the flag at write time, and a CI gate fails on it." Amended the same day with one exception list, `.ci/config/model-invocation-exceptions.json`, which holds operator rulings only, never a BLOCKER entry. The logic lives in `rediacc_ci.quality.model_invocable_commands`, and the predicate and the list loader in `.claude/rediacc_hooks/model_invocation.py`, which the two write-time guards import too.

    check_model_invocable_commands.py                  the gate over the tree and the four submodules
    check_model_invocable_commands.py --selftest       the planted controls alone
    check_model_invocable_commands.py --root <tree> --console-only    judge a fixture tree

`needs: submodules` IS LOAD-BEARING: private/account tracks a command, and an absent submodule fails the gate rather than passing unchecked. `lane: quality-code` pins the lane that checks all four submodules out in full, as check:ci-inline-suppressions does for the same reason.

---- gate ----
step: Model-invocable commands
needs: submodules
lane: quality-code
selftest: true
why: no slash command or skill is user-only (operator ruling 2026-10-09); a tracked file
     declaring disable-model-invocation fails, except an entry on the operator's exception
     list, which holds operator rulings only and is refused when stale
---- end gate ----
"""

import sys

from _cipath import CI_DIR
from rediacc_ci.quality import model_invocable_commands

if __name__ == "__main__":
    raise SystemExit(model_invocable_commands.main(sys.argv[1:], root=CI_DIR.parent))
