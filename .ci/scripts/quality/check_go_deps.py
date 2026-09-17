#!/usr/bin/env python3
"""Entry point for the ported Go dependency-freshness gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.go_deps`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 7). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.go_deps` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-go-deps.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly FOUR fields in this order: `step`, `needs`, `selftest`, `lane`. No `emit:`, no `blocker:`, no `id:`, no `run:`,
no `kind:`, no `why:`.

`lane: quality-go` IS PRESENT AND `needs: none` IS ALSO PRESENT, and that combination looks wrong until it is measured. This is a Go gate in a Go lane, so the obvious reading is that the header lost a `needs: go`. It did not. `inferredNeeds` adds `go` only for `go build`, `go vet` or `go test` (`gate-header.ts:329`), and this gate shells out to `go list -u -m -json all`, which
matches none of those. Measured on this tree, `inferredNeeds` returns `[]`
for the TWIN as well, so the twin resolves the empty set too and the two sides
agree. The declared `needs: none` is carried exactly as found rather than "corrected" upward, because widening a need here would be a new claim about the lane and not a moved one, and the twin has run in `quality-go` on that resolution all along.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-go-deps`, which is the manifest id.

`selftest: true` is inert for a `.py` gate (`gate-bind.ts:598`) and is carried because the twin declared it and because `go_deps.main(["--selftest"])` exits 0.

PINNED BY PATH, and this is the one row in this batch that a harness names. `.ci/scripts/test/gates/test-swallowed-failures.sh:44` sets
`GO_DEPS="$REPO_ROOT/.ci/scripts/quality/check-go-deps.sh"` and at line 126
counts `__PROBE_FAILED__` markers in it, asserting that the 2026-07-28 fix this gate's probe received is still present. That row does NOT run the file: it greps it. It asserts a BEHAVIOURAL NEEDLE in the source, and the needle is not in this three-line shim, so if it is ever repointed it must be repointed at the MODULE `.ci/rediacc_ci/quality/go_deps.py`, never at this entry point.
Verified by reading lines 44 and 120-130 of the harness rather than assuming. It goes on passing unchanged after this cutover because invariant 5 keeps the twin on disk, and repointing is the driver's call. `.ci/scripts/test/gates/test-go-deps-probe-failure.sh:47` copies the twin into a fixture and RUNS the copy, so that one is a run-by-path row and would have to be repointed at
the ENTRY POINT instead. Both arms are present in this single gate, which is why the brief says decide per row.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-go-deps.sh   -> exit 0
    .ci/scripts/quality/check_go_deps.py   -> exit 0
    stdout: BYTE-IDENTICAL, 404 bytes, sha256 13d96cbe6000b0fd...
    stderr: BYTE-IDENTICAL, 145 bytes, sha256 9fa3750b1d440e52...

BOTH STREAMS CARRY CONTENT ON THIS PAIR, and both were captured separately. No normalisation was applied and none was needed; the twin was first run TWICE against an unchanged tree and is byte-stable against itself on both streams.

DRIVEN RED AS WELL. The plant appends `github.com/gate/probe` to `.ci/policy/.go-deps-upgrade-blocklist` with no `# BLOCKER:` reason, which is the suppression-without-a-reason shape the BLOCKER convention exists to refuse and which this gate enforces through `verify_all_blockers`.

THE CONTROL WAS PROVED BEFORE EITHER SIDE RAN: the entry is present in the file and carries no BLOCKER annotation, checked by reading the appended bytes back rather than by trusting the append.

    both sides -> exit 1, stdout BYTE-IDENTICAL (351 bytes), stderr
    BYTE-IDENTICAL (98 bytes, sha256 4a75e32ddce015ce...):

    Go deps blocklist entries must include quality '# BLOCKER: <reason>'

The plant was reverted from a `cp` backup, verified back at its pre-plant sha256
with `sha256sum -c`, and `git status --porcelain` diffed against its pre-plant
capture with no difference.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-go-deps.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ---- step: Check Go dependency freshness needs: none selftest: true lane: quality-go
`.ci/scripts/quality/check-go-deps.sh` by an awk range over its `env-EXTERNAL_QUALITY_MODE: ${{ inputs.external_quality }}
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import go_deps

if __name__ == "__main__":
    raise SystemExit(go_deps.main(sys.argv[1:]))
