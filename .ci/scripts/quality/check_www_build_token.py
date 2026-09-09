#!/usr/bin/env python3
"""Entry point for the ported www-build-token gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.www_build_token`, which is
importable by pytest and by the port's own `--selftest`.

CUT OVER FROM BASH 2026-09-07 (W7 P4). Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-www-build-token --assert --k 5
    -> equivalence holds over 6 distinct trees

and driven again on this tree, both streams captured SEPARATELY, the twin and
this port exit 0 with byte-identical stdout and byte-identical stderr. Driven
RED as well, against a copy of `.github/workflows/` carrying one extra job that
runs `npm run build:www` with no `GITHUB_TOKEN`: both sides exit 1 and print the
same MISSING line.

THE FIRST ATTEMPT AT THAT CONTROL WAS THE UNFAIR KIND, and it is worth keeping
because it found a real defect in the twin. Pointed at a directory holding
exactly ONE `.yml`, `check-www-build-token.sh` dies with
`line 52: run: unbound variable`: `find_sites()` runs GNU grep, which prints no
filename column for a single file operand even under `-r`, so `file` becomes the
line number and `line` becomes the word `run`. The twin does not pass silently
(its own "expected at least 3 call sites" floor catches it) and the real
`.github/workflows` never has one file, so this is latent rather than live. THIS
PORT DOES NOT HAVE THAT BUG, which is one more reason the cutover is the right
direction. Do not "fix" the twin: it is the frozen comparison subject until
W7 P5 deletes it, and editing it would re-key its ledger.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-www-build-token.sh` is NOT
deleted here. It stays on disk as the differential twin; deletion is W7 P5.

---- gate ----
step: www build token
     # The EXISTING step name, lower case and all. Renaming it is a separate
     # change from moving which file it invokes.
needs: none
lane: quality-code
why: every www build must pass github.token. Found and fixed by hand at two of
     three call sites, twice, before the third reddened job 99839065246
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import www_build_token

if __name__ == "__main__":
    raise SystemExit(www_build_token.main(sys.argv[1:]))
