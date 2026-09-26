#!/usr/bin/env python3
"""Entry point for the ported release-bump-skip gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.release_bump_skip`.

CUT OVER FROM BASH 2026-09-07 (W7 P4). Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-rbs --assert --k 5
    -> equivalence holds over 7 distinct trees

and driven again on this tree, both streams captured SEPARATELY, the twin and this port exit 0 with byte-identical stdout and byte-identical stderr. Driven RED as well, through the `RELEASE_DECIDE_SCRIPT` seam against a fixture copy of dispatch-release.sh whose skip signal was reworded: both sides exit 1, report the missing signal AND the vacuity of the four anti-assertions, byte
for byte.

THAT RED RUN FOUND A REAL DIVERGENCE, now fixed in the module rather than
papered over. The twin captures with `res="$(drive "$rows")"` and command
substitution strips trailing newlines; the port kept them, so `out.split("\n")` produced a trailing empty element and the failure excerpt printed one extra six-space line per driven case. See the `.rstrip("\n")` in `rediacc_ci.quality.release_bump_skip.drive` for the measurement. It only shows on the excerpt path, which fires when dispatch-release.sh is already broken -- the one
moment the two implementations must still read as the same gate.

`test:` NOW NAMES THIS FILE, because for this gate the gate IS the test and the blocker says so. Leaving it on the twin would claim the CI coverage of a file the registry no longer invokes.

SEPARATELY, AND NOT CAUSED BY THIS CHANGE: nothing in CI actually runs this gate. `.ci/rediacc_ci/battery.py` globs `test-*.sh` inside `.ci/scripts/test/gates/`, this file is not in that directory under either name, no workflow step names `check:ci-release-bump-skip`, and the ci-runner composite is never invoked by a workflow. The blocker's "ci-quality.yml quality-security runs
the real decision every CI run" is therefore not true today and was not true before the cutover either. Reported to the driver; the fix is a battery member, which is outside this change's file set.

WHY AN ENTRY POINT AT ALL. A port cannot be run by path (`from rediacc_ci ...` fails with `.ci` off `sys.path`, which the insert below fixes), and the `-m` form that does work is unreadable to `check:ci-parity`'s tokenizer, which resolves its leaves to `[python3]`. `check_npmrc.py` records both measurements.

INVARIANT 5 IS DISCHARGED: `.ci/scripts/quality/check-release-bump-skip.sh` was the differential twin, and W7 P5 retired it.

---- gate ----
kind: test
test: .ci/scripts/quality/check_release_bump_skip.py
blocker: BLOCKER: the gate IS the test -- it drives the real dispatch-release.sh decide branch with a shimmed gh through all five paths, so ci-quality.yml quality-security runs the real decision every CI run; it exists because a bump-none merge and a broken decision both produce "no release" and only the emitted signal distinguishes them, which no release gate could see
needs: none
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import release_bump_skip

if __name__ == "__main__":
    raise SystemExit(release_bump_skip.main(sys.argv[1:]))
