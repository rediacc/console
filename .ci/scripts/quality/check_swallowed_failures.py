#!/usr/bin/env python3
"""Entry point for the ported swallowed-failures gate.

The logic lives in `rediacc_ci.quality.swallowed_failures`; this file exists so the
registry can invoke it BY PATH, for the parity-tokenizer reason recorded in
`gate-header.ts`'s `derivedRun`.

THIS GATE HAS NEVER RUN, AND THAT IS WHY IT CARRIES A HEADER WHERE ITS SIBLINGS DO NOT.
`check-swallowed-failures.sh` is invoked by NOTHING: no `package.json` key, no
`manifest.ts` entry, no workflow `run:` line, no wrapper. CI runs its gate TEST
(`gate-test:swallowed-failures`) and never the gate, so the thing that looks for probes
whose failure is indistinguishable from an empty result has itself been silently
unprotected. `check:ci-parity` cannot see it: a gate absent from BOTH sides is absent
from the comparison. Found 2026-09-08 while cutting W7 P4 over.

So this is not a cutover, it is a FIRST registration, and it goes in through a
`---- gate ----` header plus one driver `gate:bind --write` rather than by hand. Driven
against the real tree before registering: exit 0.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-swallowed-failures.sh` is NOT deleted
by this change. It stays as the twin this port is proven against; deletion is W7 P5.

THE LEDGER CONDITION IS MET. Driven 2026-09-08:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-swallowed-failures --assert --k 5
    -> equivalence holds over 10 distinct trees

---- gate ----
step: Swallowed failures
needs: none
selftest: true
lane: quality-code
why: a gate that captures a probe whose failure is indistinguishable from an empty
     result reports success it never verified. This is the scanner for that class, and
     it ran nowhere from the day it was written until 2026-09-08.
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import swallowed_failures

if __name__ == "__main__":
    raise SystemExit(swallowed_failures.main(sys.argv[1:]))
