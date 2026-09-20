#!/usr/bin/env python3
"""Entry point for the ported release-key canonicalisation gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.release_key_canonical`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 6). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.release_key_canonical` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-release-key-canonical.sh` with an awk range over its `---- gate ----` block and diffed line by line against this one. The twin carried exactly four fields -- `step`, `needs`, `selftest`, `lane` -- and no `emit:`, no `blocker:`, no `id:`, no `run:`, no `kind:`, no `why:`. The step sits INSIDE
the `# >>> gate-bind` region of `quality-security` (ci-quality.yml:1828), which is why inventing an `emit: false` here would be wrong rather than merely extra.

NO `id:` IS CORRECT HERE, checked rather than assumed: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-release-key-canonical`, the manifest id.

`selftest: true` is inert for a `.py` gate (`headerLines` emits it only for `.ts`, `gate-bind.ts:598`) and is carried because the twin declared it and because `release_key_canonical.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files rather than by reading them. `bind()` unions declared needs with `inferredNeeds(source)`; the twin's gpg body infers nothing and this two-import entry point infers nothing, because `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:301`). Both resolve to the empty set `needs: none`
declares. GPG IS NOT A DECLARABLE NEED and its absence is not an oversight: the module probes for the binary and refuses loudly with the install command in the message ("gpg is not installed, so nothing here was verified ... sudo apt-get install -y gnupg"), rather than folding a missing tool into a pass.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-release-key-canonical.sh   -> exit 0
    .ci/scripts/quality/check_release_key_canonical.py   -> exit 0
    stdout: BYTE-IDENTICAL, 823 bytes, sha256 a589d2eb1429e582...
    stderr: BYTE-IDENTICAL, and EMPTY on both sides

Byte-identical despite twelve controls that each generate a throwaway RSA key, weld it, repair it and sign with it: the key material never reaches either stream, and both sides print the same twelve control lines plus the same "(throwaway key; the real one is a secret and is deliberately out of scope)". Nothing was normalised.

DRIVEN RED AS WELL, against a HARD-COPIED FIXTURE rather than the live tree, because both implementations honour `RELEASE_KEY_ROOT`. The fixture was built
with `cp -r` and checked with `find -type l` for zero symlinks, for the reason
batch 4 paid for: `mutate-check.sh:122` resolves symlinks with `realpath --relative-to`, so a linked fixture makes a runner write into the real tree and then shows twin and port AGREEING because both read the same corrupted file.

The plant drops the `|| canon_rc=$?` guard from the canonicaliser call site in
`build-linux-pkg.sh`, which under `set -e` is exactly the shape that turns the canonicaliser's REPAIRED signal (exit 10) into an aborted build. Both sides exit 1 with BYTE-IDENTICAL 638-byte stdout and BYTE-IDENTICAL 132-byte stderr:

    FAIL  build-linux-pkg.sh guards that non-zero exit (got '0' want '1')
    release key canonicalisation: 1 of 12 control(s) failed

The fixture was restored from its `.orig` copy and `git status --porcelain` diffed against its pre-plant capture with no difference.

INVARIANT 5 HELD UNTIL THE LEDGER LICENSED THIS PORT: `.ci/scripts/quality/check-release-key-canonical.sh` stayed on disk as the differential twin until `.ci/shadow/w7p2-release-key.observations.jsonl` asserted equivalence over five distinct trees. W7 P5 batch A2 retired it, and the cases that ran it were retired with it.

---- gate ----
step: Release key canonical
needs: none
selftest: true
lane: quality-security
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import release_key_canonical

if __name__ == "__main__":
    raise SystemExit(release_key_canonical.main(sys.argv[1:]))
