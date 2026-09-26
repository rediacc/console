#!/usr/bin/env python3
"""Entry point for the `rdc.sh` wrapper-budget and `--native` platform-arm gate.

The logic lives in `rediacc_ci.quality.rdc_native`; contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it. There is no bash twin: this gate is NEW, written in the same change that moved the SEA build out of `rdc.sh`, so invariant 5 has nothing to keep.

---- gate ----
step: rdc.sh wrapper budget and --native arms
needs: none
selftest: true
lane: quality-static
why: the `--native` SEA build left rdc.sh for rediacc_ci.native, and two things
     undo that invisibly. The wrapper re-absorbs logic one special case at a
     time, which only a line ceiling catches; and the mac and win arms of that
     build have never been executed by anything in this repository, so a
     re-keyed artefact name would be found by a person with a Mac rather than
     by CI. plan() takes system and machine as arguments, so all three arms are
     driven here against a literal table read off the deleted bash
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import rdc_native

if __name__ == "__main__":
    raise SystemExit(rdc_native.main(sys.argv[1:]))
