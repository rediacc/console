#!/usr/bin/env python3
"""Entry point for the ported git-op-conditionals gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.git_op_conditionals`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 2). Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-gitop --assert --k 5
    -> 5 row(s), 5 distinct clean tree(s), 5 distinct finding set(s)
    -> equivalence holds over 5 distinct trees

THIS IS THE ONE PAIR OF THE SIX WHOSE STREAMS ARE NOT BYTE-IDENTICAL, and the difference is deliberate, documented in the port, and in the safe direction. Driven on this tree, both sides exit 0 with byte-identical STDERR; the port's stdout carries ONE extra line the twin does not print:

    ok   exempt: .ci/scripts/quality/check-git-op-conditionals.sh -- the bash
    twin of this gate: its header quotes the risky shapes as examples and its
    controls plant them in heredocs

The twin exempts ITSELF implicitly, by comparing each scanned path against
`${BASH_SOURCE[0]}`. A Python port has no such self-reference to the .sh file
that is still in the scan set, so the port names it in `EXEMPT_PATHS` with its reason and PRINTS it every run. That is the house rule for suppressions: an exemption stays visible or the gate stops meaning what its name says. It is chatter, not a finding, which is why the differential ledger reads the two sides as equivalent. When W7 P5 deletes the twin, `EXEMPT_PATHS` must be
emptied in the same change; the port's own docstring says so at the point of the constant.

DRIVEN RED AS WELL. In a fixture repository holding a copy of `.ci`, a planted `.claude/hooks/pre-bash/plant.sh` captured the current branch from `--abbrev-ref HEAD` and guarded only emptiness and the literal "main", never the literal "HEAD" a detached checkout returns. Both sides exit 1 and print the SAME finding on stderr, byte for byte:

    plant.sh:BRANCH: captures a git identity command with no guard against
    failure or the misleading HEAD literal

with the same one-line stdout difference described above and nothing else.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.git_op_conditionals` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, including `emit: false`, its `blocker:`, `needs: none`, `selftest: true` and `lane:`.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-git-op-conditionals.sh` is NOT deleted here. It stays on disk as the differential twin, and as the one path the exemption above names; deletion is W7 P5.

---- gate ---- step: Git-op conditional guards emit: false blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails. needs: none selftest: true lane: quality-code ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import git_op_conditionals

if __name__ == "__main__":
    raise SystemExit(git_op_conditionals.main(sys.argv[1:]))
