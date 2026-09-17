#!/usr/bin/env python3
"""Entry point for the ported CI-executes-only-tracked-paths gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.ci_scans_tracked_paths`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 5). See DRIVEN, below.

THE MODULE NAME DOES NOT DERIVE FROM THE TWIN BY THE USUAL RULE, so the twin was resolved from the manifest's `leaves:` and not guessed: the gate id is `check:ci-scans-tracked-paths`, the module is `ci_scans_tracked_paths`, and the twin is `check-ci-scans-tracked-paths.sh` (manifest.ts:2662). Three spellings, and dash-for-underscore maps between only two of them.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.ci_scans_tracked_paths` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THERE IS DELIBERATELY NO `---- gate ----` HEADER HERE, AND THAT IS THE CARRIED FIELD SET. The twin has no header block at all -- grepped for `---- gate ----` and for every field name, zero hits -- so the field-for-field diff comes out empty and an invented header would be a NEW claim, not a moved one. `bind()` returns null for a file with no header and the gate is simply not
gate-bind's business (`gate-bind.ts:17`).

The CI step exists and is HAND-WRITTEN, outside the `quality-static` gate-bind region (`ci-quality.yml:354`, region closes at 346), which is reported to the driver separately. That step's `run:` line is `npm run check:ci-scans-tracked-paths`, so unlike the OTLP one it follows the package.json registration and needs no workflow edit to cut over.

`inferredNeeds` NOTE, since a headerless file makes the union moot but not the fact: `inferredNeeds(twin)` is `["node"]` (its scanner matches `npm `/`npx `/ `node ` command positions in the surfaces it greps) and `inferredNeeds(this file)` is `[]`. Nothing consumes either today; recorded so a future header is written with the measured value.

DRIVEN, on this tree, both streams captured SEPARATELY:

    CI=true .ci/scripts/quality/check-ci-scans-tracked-paths.sh  -> exit 0
    CI=true .ci/scripts/quality/check_ci_scans_tracked_paths.py  -> exit 0
    stdout: byte-identical, 192 bytes (the two control lines plus the verdict)
    stderr: empty on both sides

DRIVEN RED AS WELL, and the plant carried its own negative control. A throwaway `.ci/scripts/__gate_probe_scans.sh` was written with TWO mentions of the same gitignored path: one in a comment (PROSE, which must NOT be reported) and one in command position (`bash private/growth/nope.sh`). Both sides exit 1, both print a byte-identical 136-byte stdout and a byte-identical 486-byte
stderr naming `.ci/scripts/__gate_probe_scans.sh:3` and quoting the command -- line 3, not line 2, so the prose control fired on both sides too. The probe file was then deleted and both sides returned to exit 0.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-ci-scans-tracked-paths.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import ci_scans_tracked_paths

if __name__ == "__main__":
    raise SystemExit(ci_scans_tracked_paths.main(sys.argv[1:]))
