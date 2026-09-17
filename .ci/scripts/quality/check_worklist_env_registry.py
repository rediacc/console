#!/usr/bin/env python3
"""Entry point for the WORKLIST_* environment registry gate.

The logic lives in `rediacc_ci.quality.worklist_env_registry`; this file exists so the registry can invoke it BY PATH, for the parity-tokenizer reason recorded in `gate-header.ts`'s `derivedRun` and in `_cipath`'s docstring. The `---- gate ----` header is on the MODULE.

---- gate ---- step: Worklist env registry needs: none lane: quality-static selftest: true why: 133 WORKLIST_* names are read at 183 sites with no registry and no schema.
     A typo'd name reads as unset, and for the four flags that default to `on`
     that is fail-open: the author believes they switched something off and it
     is still running
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import worklist_env_registry

if __name__ == "__main__":
    raise SystemExit(worklist_env_registry.main(sys.argv[1:]))
