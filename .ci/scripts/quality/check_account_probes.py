#!/usr/bin/env python3
"""Entry point for the ported dev-stack liveness-probe gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.account_probes`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 6). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.account_probes` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-account-probes.sh` with an awk range over its `---- gate ----` block and diffed line by line against this one. The twin carried exactly THREE fields -- `step`, `needs`, `selftest` -- and no `lane:`, no `emit:`, no `blocker:`, no `id:`, no `run:`, no `kind:`, no `why:`. The missing `lane:` is
the twin's shape and is carried: the manifest already places this step in `quality-static` and its workflow step sits inside that lane's `# >>> gate-bind` region (ci-quality.yml:240), so a lane declared here would be a new claim rather than a moved one.

NO `id:` IS CORRECT HERE, checked rather than assumed: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-account-probes`, the manifest id. Its batch-mate `check_silent_failure_patterns.py` is the one where that derivation misses.

`selftest: true` is inert for a `.py` gate (`headerLines` emits it only for `.ts`, `gate-bind.ts:598`) and is carried because the twin declared it and because `account_probes.main(["--selftest"])` exits 0, including a control that asserts a VANISHED probe library is a failure rather than a pass.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files rather than by reading them. `bind()` unions declared needs with `inferredNeeds(source)`; the twin infers nothing and this two-import entry point infers nothing, because `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:301`). Both resolve to the empty set `needs: none` declares.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-account-probes.sh   -> exit 0
    .ci/scripts/quality/check_account_probes.py   -> exit 0
    stdout: BYTE-IDENTICAL, and EMPTY on both sides
    stderr: identical after normalising the ephemeral port number only

THE STDERR IS NOT BYTE-STABLE AGAINST ITSELF, and that was demonstrated before it was worked around: the twin run TWICE against an unchanged tree prints different bytes, because two of its lines name the kernel-assigned port the probe bound (`closed port 42855` on one run, `closed port 50331` on the next). Comparing the two implementations byte for byte on that stream would
therefore have failed for a reason that has nothing to do with the port. Named exactly: the ONLY normalisation applied is `sed -E 's/port [0-9]+/port <PORT>/g'`, on both sides. Every other byte of all five lines matches, and stdout needs no normalisation at all because it is empty on both.

DRIVEN RED AS WELL, and this is the load-bearing half given an empty stdout. The plant restores the 2026-08-04 regression inside `.ci/lib/account.sh` verbatim, `|| true` back to `|| echo 000` in the curl capture, so a refused connection concatenates curl's own `000` with the fallback's and the comparison against `"000"` stops matching. Both sides exit 1, stdout stays empty on both,
and their stderr agrees on all eight lines under the same port normalisation:

    account_rustfs_alive reported ALIVE for closed port <PORT>.
    This is the 2026-08-04 defect: check for a reintroduced
    `|| echo 000` in the curl capture ...
    1 probe check(s) failed

The plant was reverted by its exact inverse, `.ci/lib/account.sh` verified back at sha256 6aef42c5c6120cbf... and `git status --porcelain` diffed against its pre-plant capture with no difference.

INVARIANT 5 IS DISCHARGED: `.ci/scripts/quality/check-account-probes.sh` was the differential twin, and W7 P5 retired it; the shadow ledger under `.ci/shadow/` is the licence record. The anti-vacuity harness that pinned the twin BY PATH was repointed at this entry point first, so
`.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py` asserts the "nothing to check" diagnostic against this file and the retirement leaves no row exercising a file that is gone. That harness was itself a bash twin until 2026-09-21; the registry is now the port's alone.

---- gate ----
step: Dev-stack liveness probes
needs: none
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import account_probes

if __name__ == "__main__":
    raise SystemExit(account_probes.main(sys.argv[1:]))
