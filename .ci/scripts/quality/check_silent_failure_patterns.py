#!/usr/bin/env python3
"""Entry point for the ported silent-failure-pattern gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.silent_failure_patterns`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 6). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.silent_failure_patterns` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-silent-failure-patterns.sh` with an awk range over its `---- gate ----` block and diffed line by line against this one, INCLUDING THE FIELD ORDER, which the twin writes as step / needs / id / selftest. The twin carried exactly those four and no `emit:`, no `blocker:`, no `run:`, no `kind:`,
no `why:` -- and, the presence that matters here, NO `lane:`.

`id: check:ci-silent-failures` IS THE FIELD THIS GATE WOULD DIE WITHOUT, and it is the reason the task brief warned that the dash-for-underscore convention does not always hold. `derivedId` (`gate-header.ts:260`) turns this basename into `check:ci-silent-failure-patterns`; the manifest id is `check:ci-silent-failures`. Drop the line and the header binds to an id the manifest does
not have, which is a parity failure in the lucky case and a gate bound to nothing in the unlucky one. The twin needed the same line for the same reason, its own basename being `check-silent-failure-patterns.sh`.

NO `lane:` IS ALSO CARRIED. The twin declares none, the manifest already places the step in `quality-static` (ci-quality.yml:327, inside that lane's `# >>> gate-bind` region), and adding a lane here would be a new claim rather than a moved one. `selftest: true` is inert for `.py` (`headerLines` emits it only for `.ts`, `gate-bind.ts:598`) and is carried because the twin declared it
and because `silent_failure_patterns.main(["--selftest"])` really does exit 0 over a control battery.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files rather than by reading them. `bind()` unions the declared needs with `inferredNeeds(source)`; the twin's `find`/`awk` body infers nothing, and this two-import entry point infers nothing because `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:301`). Both resolve to the empty set.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-silent-failure-patterns.sh   -> exit 0
    .ci/scripts/quality/check_silent_failure_patterns.py   -> exit 0
    stdout: BYTE-IDENTICAL, and EMPTY on both sides
    stderr: BYTE-IDENTICAL, 79 bytes (the single clean verdict line)

THE EMPTY STDOUT IS EXACTLY WHY THE STREAMS ARE CAPTURED APART, and why the clean run proves almost nothing on its own: this gate puts its whole verdict on stderr, so a merged comparison would have compared log lines and a stdout-only comparison of merged output would have compared nothing.

ARGUMENT HANDLING WAS DRIVEN TOO, because this is one of the few ported gates that takes any. `--json` gives exit 0 with a byte-identical 29-byte stdout on both sides, and an unknown argument gives exit 2 (NOT 1) with a byte-identical 29-byte stderr on both sides. The twin's odd exit-2-for-usage is preserved rather than tidied.

DRIVEN RED AS WELL, by a probe script at `.ci/scripts/quality/__gate_probe_silent_failure_w7p4b6.sh` carrying
`set -euo pipefail` and then `count=$(find . -name '*.txt' | wc -l)`, the
unguarded pipefail-risk pipeline this gate exists for. Both sides exit 1 with stdout still empty and BYTE-IDENTICAL 585-byte stderr, naming the same file, the same line 3 and the same three remedies. The probe was deleted afterwards and `git status --porcelain` diffed against its pre-plant capture with no difference.

INVARIANT 5 IS DISCHARGED: `.ci/scripts/quality/check-silent-failure-patterns.sh` was the differential twin, and W7 P5 retired it; the shadow ledger under `.ci/shadow/` is the licence record.

---- gate ----
step: Silent-failure patterns
needs: none
id: check:ci-silent-failures
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import silent_failure_patterns

if __name__ == "__main__":
    raise SystemExit(silent_failure_patterns.main(sys.argv[1:]))
