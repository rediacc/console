#!/usr/bin/env python3
"""Entry point for the ported baked-OTLP-credential gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.no_otlp_creds`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 5). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.no_otlp_creds` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THERE IS DELIBERATELY NO `---- gate ----` HEADER HERE, AND THAT IS THE CARRIED FIELD SET. The twin has no header block at all -- grepped for `---- gate ----` and for every field name, zero hits -- so the field-for-field diff comes out empty and an invented header would be a NEW claim, not a moved one. `bind()` returns null for a file with no header and the gate is simply not
gate-bind's business (`gate-bind.ts:17`), which is the twin's status today and must stay the port's.

That absence is correct for this gate specifically: its CI step lives in `.github/workflows/ci-build-renet.yml`, a workflow with NO `# >>> gate-bind` region anywhere in it, so there is no region for a header to emit into. It is also the reason the step is HAND-WRITTEN, which is reported to the driver separately: gate-bind matches a step by NAME only, never its `run:` line, so that
step keeps invoking the twin until a human edits it.

`inferredNeeds` NOTE, since a headerless file makes the union moot but not the fact: `inferredNeeds(twin)` is `["submodules"]` (its body names `private/renet`) and `inferredNeeds(this file)` is `[]`. Nothing consumes either, because neither file declares a header, but the shrink is recorded here so a future header is written with `needs: submodules` rather than derived from this
file's imports.

DRIVEN, on this tree, both streams captured SEPARATELY, and NOT vacuously: the tree carries seven real renet binaries and a real 16 MB CLI bundle, so both sides inspected eight artifacts rather than warning and skipping.

    CI=true .ci/scripts/quality/check-no-otlp-creds.sh  -> exit 0
    CI=true .ci/scripts/quality/check_no_otlp_creds.py  -> exit 0
    stdout: byte-identical, EMPTY on both sides
    stderr: byte-identical, 505 bytes, including the seven `inspecting
      renet-*` lines IN THE SAME ORDER (the twin's `find -maxdepth 1` order and
      the port's enumeration order agreed on every run, green and red)

DRIVEN RED AS WELL, by appending one literal `Authorization: Basic <44-char base64>` assignment to `packages/cli/dist/cli-bundle.cjs` (a gitignored build artifact, backed up with `cp -p` first). Both sides exit 1, both print an EMPTY stdout, and their stderr is byte-identical at 746 bytes: the seven renet binaries still clear, the bundle line reds, and the tally reads `1 credential
leak(s) detected`. The bundle was restored from the backup and verified by sha256 (2335043dd2b426247447c3f0cc3f2498a875fa13b7fd8ee7828ff03b5c3067b7), with the twin back at exit 0.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-no-otlp-creds.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import no_otlp_creds

if __name__ == "__main__":
    raise SystemExit(no_otlp_creds.main(sys.argv[1:]))
