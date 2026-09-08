#!/usr/bin/env python3
"""Entry point for the ported e2e-tests coverage gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.e2e_coverage`, which pytest and
the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 6). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port
cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below),
and `python3 -m rediacc_ci.quality.e2e_coverage` works but is the wrong
registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves
the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from
`.ci/scripts/quality/check-e2e-coverage.sh` with an awk range over its
`---- gate ----` block and diffed line by line against this one. The twin
carried exactly four fields -- `step`, `needs`, `selftest`, `lane` -- and no
`emit:`, no `blocker:`, no `id:`, no `run:`, no `kind:`, no `why:`. That
shortness is the twin's shape rather than an omission, and the absences are
carried as deliberately as the presences: inventing an `emit: false` here would
claim a hand-written step this gate does not have (its step sits INSIDE the
`# >>> gate-bind` region of `quality-content`, ci-quality.yml:1056).

NO `id:` IS CORRECT HERE, checked rather than assumed: `derivedId`
(`gate-header.ts:260`) maps this basename to `check:ci-e2e-coverage`, the
manifest id.

`needs: node, submodules` IS THE LOAD-BEARING FIELD OF THIS BATCH. The twin got
both for free from its own body: `npx tsx scripts/check-e2e-coverage.ts` matches
the node pattern and its prose names `private/renet`. This entry point contains
NEITHER string outside its docstring, and `inferredNeeds` strips Python
docstrings as prose (`gate-header.ts:301`), so it infers NOTHING at all. Copied
verbatim, and verified by calling `bind()` on both files rather than by reading
them: both sides resolve to {node, submodules}. Lose this line and the gate is
placed in a lane with no node and no submodule, where it would fail at
`npx tsx` or, worse, sweep an absent `packages/e2e-tests` and report coverage
over nothing.

`selftest: true` is inert for a `.py` gate (`headerLines` emits it only for
`.ts`, `gate-bind.ts:598`) and is carried because the twin declared it and
because it is true: `e2e_coverage.main(["--selftest"])` exits 0.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-e2e-coverage.sh   -> exit 0
    .ci/scripts/quality/check_e2e_coverage.py   -> exit 0
    stdout: BYTE-IDENTICAL, 1029 bytes, sha256 94a6ff97af074863...
    stderr: BYTE-IDENTICAL, 342 bytes

Byte-identical INCLUDING the colour escapes, which is not luck: the forward half
of this gate is `npx tsx scripts/check-e2e-coverage.ts` with its streams
INHERITED, so the coloured block on stdout is written by the same TypeScript
process in both runs. Nothing was normalised here.

DRIVEN RED AS WELL, by a probe file under `packages/e2e-tests/tests/` dispatching
`function: 'gate_probe_dead_verb_w7p4b6'`, a verb no renet registry entry
defines. Both sides exit 1, stdout stays byte-identical and stderr grows to the
same 695 bytes naming the same finding:

    e2e-tests dispatch 1 verb(s) that renet no longer registers:
      - gate_probe_dead_verb_w7p4b6  ... tests/__gate_probe_e2e_coverage_w7p4b6.ts:1

THE FIRST PLANT DID NOT FIRE, AND THE FAULT WAS THE CONTROL, NOT THE GATE. It
was written to `packages/e2e-tests/` itself, and the reverse sweep walks
`E2E_SUBDIRS = ("src", "tests")` (`e2e_coverage.py:159`), never the package root.
Both sides stayed green and briefly looked like a gate that could not fail;
moving the probe one directory down turned both red at once. Recorded because
the next reader will reach for the package root too.

The probe was deleted and `git status --porcelain` diffed against its pre-plant
capture with no difference.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-e2e-coverage.sh` is NOT deleted
here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Check E2E test coverage for all renet functions
needs: node, submodules
selftest: true
lane: quality-content
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import e2e_coverage

if __name__ == "__main__":
    raise SystemExit(e2e_coverage.main(sys.argv[1:]))
