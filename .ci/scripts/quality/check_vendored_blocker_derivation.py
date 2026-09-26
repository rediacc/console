#!/usr/bin/env python3
"""Entry point for the vendored blocker derivation gate.

The logic lives in `rediacc_ci.quality.vendored_blocker_derivation`; this file exists so the registry can invoke it BY PATH, for the parity-tokenizer reason recorded in `gate-header.ts`'s `derivedRun` and in `_cipath`'s docstring.

---- gate ----
step: Vendored blocker derivation
needs: none
lane: quality-static
selftest: true
why: the golden corpus pins the vendored breakpoint validator as differing from
     canonical on "exactly five" cases, which is a magic number: it says which
     count, never which five, and it cannot see one row leaving as another
     arrives. This DERIVES the five from the two list facts that cause them --
     the vendored copy drops twelve canonical phrases and has no substring list
     at all -- so a divergence that stops being explained is a finding rather
     than a repin, and it reads and hashes .ci/breakpoint/ without writing to it
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import vendored_blocker_derivation

if __name__ == "__main__":
    raise SystemExit(vendored_blocker_derivation.main(sys.argv[1:]))
