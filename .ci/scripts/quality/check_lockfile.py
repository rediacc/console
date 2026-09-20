#!/usr/bin/env python3
"""Entry point for the ported lockfile gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.lockfile`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 7). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.lockfile` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-lockfile.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly THREE fields in this order: `step`, `needs`, `selftest`. No `lane:`, no `emit:`, no `blocker:`, no `id:`, no
`run:`, no `kind:`, no `why:`.

`needs: node` IS THE FIELD THIS PAIR EXISTS TO WARN ABOUT, and it is the reason finding 2 of the batch brief is not theoretical. `bind()` unions the declared needs with `inferredNeeds(source)`. The TWIN gets `node` for free from its own body: it runs `npm ci --dry-run` under two npm majors, so the inference fires whether or not the header declares it. Measured on this tree,
`inferredNeeds` returns `[node]` for the twin and `[]` for this entry point, because the entry point's only mention of npm is inside a docstring and `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:301`). Had `needs: node` been
dropped in the move, the twin would still have resolved `{node}` and this port
would have resolved the EMPTY SET, quietly placing a gate that shells out to npm
into a lane with no node runtime. Carried whole, both sides resolve to `{node}`,
verified by calling `bind()` on both files and comparing every field but `file` and `run`.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-lockfile`, which is the manifest id.

`selftest: true` is inert for a `.py` gate (`gate-bind.ts:598`) and is carried because the twin declared it and because `lockfile.main(["--selftest"])` exits 0.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both.
READ THE EXIT CODE BEFORE THE VERDICT: THIS TREE IS ALREADY RED, for a reason that predates this cutover and has nothing to do with it.

    .ci/scripts/quality/check-lockfile.sh   -> exit 1
    .ci/scripts/quality/check_lockfile.py   -> exit 1
    stdout: BYTE-IDENTICAL, 2542 bytes, sha256 43afea596a4603bb...
    stderr: BYTE-IDENTICAL, 5293 bytes, sha256 4fe911d76023c907...
    verdict, identical on both sides:
      Lockfile check FAILED for: private/account/package-lock.json
      (npm@10 cannot resolve)

THE PRE-EXISTING FAILURE IS IN A SUBMODULE THIS BATCH DID NOT TOUCH.
`private/account/package-lock.json` is missing the `@esbuild/*` platform packages npm 10 demands, and `private/account` is a modified submodule in this working tree. It is reported as a finding rather than smoothed over, and it is the reason the honest claim for this pair is "the two implementations agree", not "the gate is green".

SO THE GREEN-SIDE DIFFERENTIAL IS NOT AVAILABLE HERE, and saying so is the point of the ledger. What IS available is two independent RED differentials, both byte-identical across 7835 bytes of output, which is a stronger agreement sample than most green comparisons in this programme.

NO NORMALISATION WAS APPLIED and none was needed, which is itself a measured result rather than an assumption: the twin was run TWICE against an unchanged tree and is byte-stable on both streams, timings included, because it reports per-lockfile verdicts and not durations.

DRIVEN RED AGAIN UNDER A PLANT, to show the two sides agree on a finding that was not already there. The plant bumps `wrangler` from `^4.67.0` to `^4.99.0` in `workers/mta-sts/package.json` and leaves `workers/mta-sts/package-lock.json` alone, which is exactly the manifest-without-lockfile-edit defect the manifest's `paths:` entry for `**/package.json` exists to catch.

THE CONTROL WAS PROVED BEFORE EITHER SIDE RAN, on both halves: the manifest carries the new range, and the lockfile still pins the old one.

    both sides -> exit 1, stdout BYTE-IDENTICAL (5281 bytes), stderr
    BYTE-IDENTICAL (5304 bytes), verdict identical on both:
      Lockfile check FAILED for: private/account/package-lock.json
      (npm@10 cannot resolve) workers/mta-sts/package-lock.json
      (npm@11 cannot resolve)

The added clause is the proof the plant landed: diffing the planted verdict against the unplanted one shows exactly one new lockfile named, and nothing
else moved. The plant was reverted from a `cp` backup, verified back at its
pre-plant sha256 with `sha256sum -c`, and `git status --porcelain` diffed against its pre-plant capture with no difference.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-lockfile.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Lockfile
needs: node
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import lockfile

if __name__ == "__main__":
    raise SystemExit(lockfile.main(sys.argv[1:]))
