#!/usr/bin/env python3
"""Entry point for the ported gate-id-convention gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.gate_id_convention`, which pytest and the
port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8a, the broad tree-scanning nine). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.gate_id_convention` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-gate-id-convention.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly THREE fields in this order: `step`, `needs`, `selftest`. No `emit:`, no `blocker:`, no `id:`, no
`run:`, no `kind:`, no `lane:`, no `why:`.

NO `lane:` IS CORRECT: the step sits inside the `# >>> gate-bind` region of `quality-static` (ci-quality.yml:199-346), so the lane comes from the region.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-gate-id-convention`, which is the manifest id.

`selftest: true` is inert for a `.py` gate (`gate-bind.ts:598`) and is carried because the twin declared it and because `gate_id_convention.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files. Both infer `[]` and both resolve to the empty set `needs: none` declares.

THIS ENTRY POINT IS A SUBJECT OF THE GATE IT REGISTERS, which is the one thing worth checking twice here: this gate reads the registry and asserts every gate id follows the convention. Adding a ninth `.py` entry point in this batch does not change the id set at all, because the id is derived from the basename and this basename derives the id the manifest already carries. Verified
behaviourally: the shape line the gate prints is identical on both sides of the cutover with all nine of this batch's entry points on disk.

PINNED BY PATH IN ONE HARNESS, and it is a DIFFERENTIAL. `.ci/rediacc_ci/tests/test_quality_gate_id_convention.py:29` sets
`TWIN = paths.from_root(".ci", "scripts", "quality", "check-gate-id-convention.sh")`
and MUST KEEP NAMING THE TWIN. `.ci/scripts/test/gates/test-shrink-only-composition.sh:66` mentions the twin in a prose comment only and pins nothing.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-gate-id-convention.sh   -> exit 0
    .ci/scripts/quality/check_gate_id_convention.py   -> exit 0
    stdout: BYTE-IDENTICAL, 322 bytes, sha256 b7ace97659e3bc76...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

    ✓ every gates.lock.json entry that runs a gates/ script uses the
      gate-test: convention
      scope: SUBJECTS 149 of 461 entries, floor 149
      control 1 fired on the planted check:ci-* alias (2 finding(s))
      control 2 fired the corpus floor on a truncated lock

THAT SCOPE LINE IS THE ANTI-VACUITY EVIDENCE, and it is identical on both sides, which is what makes the comparison mean something: a corpus that had silently collapsed across the cutover would print different numbers.

No normalisation was applied and none was needed; the twin was run TWICE against
an unchanged tree and is byte-stable against itself on both streams.

A PORT GAP WAS FOUND DOING THIS AND FIXED IN `gate_id_convention.py`. The first comparison came back 322 bytes against 311: same exit code, same words, and ELEVEN BYTES of ANSI escape missing. The twin assigns `RED`/`GREEN`/`NC` at check-gate-id-convention.sh:81-83 with no tty test, so it writes colour into a
pipe; the port printed the glyphs bare. Eleven bytes is not cosmetic when the
bar is byte identity, and TTY-gating one side during a move is a behaviour change smuggled into a file move. The module now carries the same three unconditional constants and uses them at all three sites (the `fail` cross, the findings cross, the success tick), matching `shell_size.py`'s precedent.

DRIVEN RED AS WELL, in a `cp -r` fixture root and not on the real tree: the twin copied to `.ci/scripts/quality/` so its `$BASH_SOURCE` root is the fixture, plus `package.json`, `.ci/scripts/test/` and `scripts/ci-runner/gates.lock.json`. The port is aimed at the same tree with `REDIACC_CI_ROOT`. The plant appends ONE entry to the fixture lock: id `check:ci-probe-8a-alias`, `run`
pointing straight at `.ci/scripts/test/gates/test-dead-case-arms.sh`.

THE FIRST PLANT DID NOT FIRE, AND THE CONTROL WAS WRONG, NOT THE GATE. It named the gates/ script in `leaves` and left `run` as an npm alias with no matching
package.json script. Subject-hood is decided by `resolves_to_gate_script(run)`
(check-gate-id-convention.sh:145), which reads `run` and never looks at `leaves`, so the entry was simply not a subject and both sides correctly stayed green. The repaired plant was checked against the gate's OWN predicate, evaluated in isolation before either side ran: `resolves_to_gate_script` returns True for the plant's `run`, and the plant's id does not start with
`gate-test:`.

    both sides -> exit 1, stdout EMPTY on both, stderr BYTE-IDENTICAL
    (569 bytes, sha256 d14f69604eb80187...):

    ✗ gate registration does not follow the gates/ convention:
      CONVENTION: 'check:ci-probe-8a-alias' runs a gates/ script but is not
      registered as gate-test:<name> (149 siblings are)

That red run also re-proves the colour fix on the FAILURE path, where the cross is escaped identically on both sides.

THE REAL TREE WAS NEVER WRITTEN TO for this gate: `scripts/ci-runner/gates.lock.json` is untouched by this change and the planted copy lives only under the fixture.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-gate-id-convention.sh` is NOT deleted
here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ---- step: Gate registration follows the gates/ convention needs: none selftest: true ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import gate_id_convention

if __name__ == "__main__":
    raise SystemExit(gate_id_convention.main(sys.argv[1:]))
