#!/usr/bin/env python3
"""Entry point for the hook cross-OS seam gate.

The logic lives in `rediacc_ci.quality.hook_cross_os`; this file exists so the registry can invoke it BY PATH, for the parity-tokenizer reason recorded in `gate-header.ts`'s `derivedRun` and in `_cipath`'s docstring. The `---- gate ----` header is on the MODULE.

---- gate ---- step: Hook cross-OS seams needs: none lane: quality-static selftest: true why: .claude/rediacc_hooks has exactly one platform seam today and nothing was
     keeping it that way. A `/proc` read added to a guard works for every
     reviewer, because every reviewer is on Linux, and fails silently on macOS
     by finding nothing rather than by erroring
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import hook_cross_os

if __name__ == "__main__":
    raise SystemExit(hook_cross_os.main(sys.argv[1:]))
