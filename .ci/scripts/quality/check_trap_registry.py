#!/usr/bin/env python3
"""Entry point for the ported trap-registry disposition gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.trap_registry`, which pytest and the
port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8a, the broad tree-scanning nine). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.trap_registry` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-trap-registry.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried SEVEN fields in this order: `step`, `emit`, `blocker`, `needs`, `selftest`, `lane`, `why`. THE `why:`
IS ELEVEN CONTINUATION LINES and it is the largest header in this batch; every
one of those lines is carried, indentation included, because a `why:` truncated to its first line still parses and still binds and would lose the argument for the deliberate absence of `paths`.

`emit: false` PLUS ITS `blocker:` ARE THE PAIR THE PILOT LOST. This gate's step is HAND-WRITTEN at ci-quality.yml:676, which is ABOVE the `quality-code` `# >>> gate-bind` region (739-916) and therefore above that lane's `- id: setup` guard. Emitting it into the region would move it below the guard and skip it whenever setup fails. Confirmed by line arithmetic against the region
markers, not by trusting the field: 676 is outside 739-916.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-trap-registry`, which is the manifest id.

`selftest: true` is inert for a `.py` gate (`gate-bind.ts:598`) and is carried because the twin declared it and because `trap_registry.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files. Both infer `[]` and both resolve to the empty set `needs: none` declares.

`TRAP_FLOOR` IS NOT TOUCHED BY THIS CHANGE. It is 79, it lives in BOTH `.ci/scripts/quality/check-trap-registry.sh` and `.ci/rediacc_ci/quality/trap_registry.py`, and `.ci/rediacc_ci/tests/test_quality_trap_registry.py` asserts the two agree.
Neither number was edited here; this entry point adds no third copy.

PINNED BY PATH IN THREE PLACES, split across two arms:

  - RUN-IN-PLACE, so ENTRY POINT if repointed:
    `.ci/scripts/test/gates/test-trap-registry.sh:34` (`GATE=`, then runs it)
    `.ci/rediacc_ci/tests/gates/test_gate_trap_registry.py:68` (`GATE_REL`)
  - DIFFERENTIAL, so it MUST KEEP NAMING THE TWIN:
    `.ci/rediacc_ci/tests/test_quality_trap_registry.py:21`

Unlike this batch's three `kind: test` gates, this one has its own workflow step, so CI runs whatever the step's `run:` line names. That line is `npm run check:ci-trap-registry`, an indirection through package.json, so the driver's package.json edit moves the CI side too and no workflow edit is needed.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-trap-registry.sh   -> exit 0
    .ci/scripts/quality/check_trap_registry.py   -> exit 0
    stdout: BYTE-IDENTICAL, EMPTY on both sides
    stderr: BYTE-IDENTICAL, 243 bytes, sha256 cafd9ecb08ff4eaf...

No normalisation was applied and none was needed; the twin was run TWICE against
an unchanged tree and is byte-stable against itself on both streams.

DRIVEN RED AS WELL, through the twin's own `TRAP_CORPUS` seam, which the port reads under the same name. The fixture is a `cp` of the real `docs/agent-reference/TRAPS.md` with ONE pointer re-aimed: the `check-cannot-fail` entry's first `gate:` becomes `gate:check:ci-gate-probe-8a-does-not-exist`.

THE CONTROL WAS PROVED ON BOTH OF ITS PRECONDITIONS BEFORE EITHER SIDE RAN. A
`diff` against the real file shows EXACTLY ONE changed line, so nothing else
about the corpus moved; the planted id appears ZERO times in both
`scripts/ci-runner/manifest.ts` and `package.json`, so it genuinely dangles; and
the fixture still carries 79 `## ` entries, so the corpus FLOOR is satisfied and the red below is the pointer check rather than the floor. That last one matters: a plant that dropped the count would have produced a red that said nothing about pointers.

    both sides -> exit 1, stdout EMPTY on both, stderr BYTE-IDENTICAL
    (477 bytes, sha256 250c23d2d55702c8...):

    ✓ controls: 19 planted defects red, 2 clean fixtures green
    ✗ <fixture>:69: 'check-cannot-fail' names
      gate:check:ci-gate-probe-8a-does-not-exist, which is not both a manifest
      entry and a package.json script. A dangling pointer is a lie about coverage.

THE REAL TREE WAS NEVER WRITTEN TO for this gate. `docs/agent-reference/TRAPS.md` is untouched, and so is `TRAP_FLOOR` in both of the two places it lives.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-trap-registry.sh` is NOT deleted
here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ---- step: Trap registry dispositions emit: false blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails. needs: none selftest: true lane: quality-code why: TRAPS.md is a REGISTRY, not prose: every `## ` entry
names the instrument
     that enforces it, and the gate proves that pointer RESOLVES and is LIVE.
     Presence alone would be worse than nothing -- the cheapest thing to name
     under a coverage gate is a check that cannot fire -- so a gate: pointer
     must be scheduled by `npm run ci`, a hook: rule must have both a firing
     and a silent case, and a file: pointer must be reachable from something
     that runs it. No `paths`, deliberately: pointers resolve against the
     manifest, package.json, the dispatcher, the hook suite and settings.json,
     so almost any change can dangle one, and a half-populated path table
     would drop the gate from --changed exactly when it was needed.
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import trap_registry

if __name__ == "__main__":
    raise SystemExit(trap_registry.main(sys.argv[1:]))
