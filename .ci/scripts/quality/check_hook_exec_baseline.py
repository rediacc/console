#!/usr/bin/env python3
"""Entry point for the hook exec baseline gate.

The logic lives in `rediacc_ci.quality.hook_exec_baseline`; this file exists so the
registry can invoke it BY PATH, for the parity-tokenizer reason recorded in
`gate-header.ts`'s `derivedRun` and in `_cipath`'s docstring.

The `---- gate ----` header is on the MODULE rather than here, which is the shape
`check-swallowed-failures` and the rest of the ported family use.

---- gate ----
step: Hook exec baseline
needs: none
lane: quality-static
selftest: true
why: W5's "2 processes per Bash tool call" target had no baseline in the tree at
     all, so the cost of the hook wiring could grow without anything noticing.
     This pins the per-tool and per-event process counts derived from
     .claude/settings.json and refuses in both directions, so a collapse has to
     be claimed and a regression cannot be quiet
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import hook_exec_baseline

if __name__ == "__main__":
    raise SystemExit(hook_exec_baseline.main(sys.argv[1:]))
