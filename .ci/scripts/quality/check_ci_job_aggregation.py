#!/usr/bin/env python3
"""Entry point for the ported CI job-aggregation gate.

The logic lives in `rediacc_ci.quality.ci_job_aggregation`; this file exists so the registry can invoke it BY PATH, which is the only invocation form `check-ci-parity`'s tokenizer can read (`gate-header.ts`'s `derivedRun` records why a `-m` command resolves its leaves to `[python3]` and fails parity).

THIS GATE HAS NEVER RUN, AND THAT IS WHY IT CARRIES A HEADER WHERE ITS SIBLINGS DO NOT.
`check-ci-job-aggregation.sh` is invoked by NOTHING: no `package.json` key, no `manifest.ts` entry, no workflow `run:` line, no wrapper. CI runs its gate TEST (`gate-test:ci-job-aggregation`) and never the gate, so its logic has been exercised against fixtures while never once judging the real repository -- and `check:ci-parity` cannot see that, because a gate absent from BOTH
sides is absent from the comparison. Found 2026-09-08 while cutting W7 P4 over: it was one of only three of the last thirteen twins with no registration to repoint.

So this is not a cutover, it is a FIRST registration, and it goes in through a `---- gate ----` header plus one driver `gate:bind --write` rather than by hand. Driven against the real tree before registering: exit 0.

INVARIANT 5 IS DISCHARGED, W7 P5. `.ci/scripts/quality/check-ci-job-aggregation.sh` and its gate test `.ci/scripts/test/gates/test-ci-job-aggregation.sh` are both deleted: the fixture behaviour the test proved is now carried by `.ci/rediacc_ci/tests/gates/test_gate_ci_job_aggregation.py`, retargeted at this Python entry point and checked to reach the same 15 verdicts on the same 15
fixtures before the twin left.

THE LEDGER CONDITION WAS MET. Driven 2026-09-08:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-ci-job-aggregation --assert --k 5
    -> equivalence holds over 5 distinct trees

---- gate ----
step: CI job aggregation
needs: none
id: check:ci-job-aggregation
selftest: true
lane: quality-code
why: every non-exempt job in ci.yml must be aggregated by ci-complete and tiered, or a
     job can fail while the pipeline reports success. The gate existed and ran nowhere
     from the day it was written until 2026-09-08.
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import ci_job_aggregation

if __name__ == "__main__":
    raise SystemExit(ci_job_aggregation.main(sys.argv[1:]))
