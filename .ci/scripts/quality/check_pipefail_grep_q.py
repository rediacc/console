#!/usr/bin/env python3
"""Entry point for the ported pipefail/grep -q gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.pipefail_grep_q`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 2). Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-pipefail-grepq --assert --k 5
    -> 5 row(s), 5 distinct clean tree(s), 5 distinct finding set(s)
    -> equivalence holds over 5 distinct trees

and driven again on this tree, both streams captured SEPARATELY: the twin and this port exit 0 with byte-identical stdout and byte-identical stderr (753 bytes of stdout, 0 of stderr).

DRIVEN RED AS WELL, and THE FIRST CONTROL DID NOT FIRE, which was a fault in the control and not in the gate. The plant went to `scripts/plant.sh`; the corpus pathspec is `scripts/**/*.sh`, and git without `:(glob)` magic reads that as `scripts/` + anything + `/` + anything + `.sh`, so a file at depth one under `scripts/` matches NOTHING. Listing the tracked files under that
pathspec printed nothing for it, which is the proof rather than the guess. (The pathspec is quoted here WITHOUT the enumeration command on the same line, because `check:ci-pathspec-scope` reads a quoted pathspec beside a `ls-files` call as a USE and would flag this prose. That gate is right about the shape and cannot see either of the two live instances; see the report accompanying
this cutover.) Moved to `scripts/dev/plant.sh` (pipefail set, a local `emit()` producer, and `emit | grep -q needle`) and both sides then exit 1, naming `scripts/dev/plant.sh:6`, with byte-identical stdout and stderr.

THAT PATHSPEC HOLE IS REAL AND IS NOT THIS PORT'S: the twin has it too, which is why the differential stays equivalent. Two tracked shell files sit at depth one under `.claude/hooks/` -- `chain-head.sh` and `test-hooks.sh` -- and neither is in this gate's corpus. Neither carries the racing shape today (checked: the head does not set pipefail at all, and
`test-hooks.sh`'s `grep -q` uses are herestrings, not local-function producers), so the hole is latent rather than live. Widening the pathspec is a change to BOTH sides and would re-key the ledger, so it is not folded into a cutover.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.pipefail_grep_q` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, including `emit: false`, its `blocker:`, `needs: none`, `selftest: true`, `lane:` and the whole `why:` block.

INVARIANT 5 HELD UNTIL THE LEDGER LICENSED THIS PORT: `.ci/scripts/quality/check-pipefail-grep-q.sh` stayed on disk as the differential twin until `.ci/shadow/w7p2-pipefail-grepq.observations.jsonl` asserted equivalence over five distinct trees. W7 P5 batch A2 retired it, and the cases that ran it were retired with it.

---- gate ----
step: No racing pipefail/grep -q detectors
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails.
needs: none
selftest: true
lane: quality-code
why: A detector built as `producer | grep -q` under pipefail cannot reliably
     fail: grep -q exits at its first match, SIGPIPEs the producer, and
     pipefail makes that 141 the verdict. check-ci-watch-recipe.sh shipped
     exactly that in both detectors and certified 124 files clean over a real
     offender for as long as it existed.
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import pipefail_grep_q

if __name__ == "__main__":
    raise SystemExit(pipefail_grep_q.main(sys.argv[1:]))
