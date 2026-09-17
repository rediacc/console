#!/usr/bin/env python3
"""Entry point for the ported content-quality (AI slop) gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.content_quality`, which pytest and the
port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8a, the broad tree-scanning nine).
See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port
cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below),
and `python3 -m rediacc_ci.quality.content_quality` works but is the wrong registration
because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to
`[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from
`.ci/scripts/quality/check-content-quality.sh` by an awk range over its
`---- gate ----` block, de-commented, and diffed as an ordered list of whole
lines against the block in this docstring. The twin carried exactly FOUR fields
in this order: `step`, `needs`, `selftest`, `lane`. No `emit:`, no `blocker:`,
no `id:`, no `run:`, no `kind:`, no `why:`.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename
to `check:ci-content-quality`, which is the manifest id.

`selftest: true` is inert for a `.py` gate (`gate-bind.ts:598`) and is carried
because the twin declared it and because
`content_quality.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files.
Both infer `[]` and both resolve to the empty set `needs: none` declares.

THIS ENTRY POINT COULD HAVE ENTERED THE GATE'S OWN CORPUS, and that was the
first thing checked, because this gate sweeps prose for AI-slop patterns and a
docstring this long is prose. It does not: the corpus is content under the
documentation and marketing trees, not `.ci/scripts/quality/`. Verified
behaviourally rather than by reading the glob, by the file count in the gate's
shape line being identical on both sides of the cutover with all nine of this
batch's entry points already on disk. That matters more here than elsewhere: a
corpus that silently grew or shrank across the cutover would make the
differential meaningless.

PINNED BY PATH NOWHERE THAT RUNS IT. The only reference outside the workflow is
`.ci/rediacc_ci/tests/test_quality_content_quality.py:38`, a comment recording
that the exemption program is copied verbatim from `check-content-quality.sh`
lines 111-118, and that module is the DIFFERENTIAL, which must keep naming the
twin regardless. Nothing under `.ci/scripts/test/gates/` names this gate.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both.
THIS IS THE ONE PAIR IN THE BATCH THAT IS NOT BYTE-IDENTICAL, and the difference
is ORDER ONLY. Stated plainly rather than folded into a pass:

    .ci/scripts/quality/check-content-quality.sh   -> exit 0
    .ci/scripts/quality/check_content_quality.py   -> exit 0
    stdout: 1141 bytes on BOTH sides, different sha256
    stderr:  598 bytes on BOTH sides, different sha256

THE TWIN IS BYTE-STABLE AGAINST ITSELF, checked first and on both streams, and
each side reproduces its own bytes exactly across runs. So this is not flake and
it is not a peer's plant window; it was re-run and is deterministic on each side.

WHAT DIFFERS IS THE FILE ENUMERATION ORDER, and the port's is deliberate.
`discover()` documents it: the twin's `find` emits in readdir order, which is
filesystem state rather than repository content, so the port sorts. Measured
here rather than taken on trust: raw `find` over the two content roots is NOT
lexicographic on this tree (1107 files, first entry `docs/ru/account-management.md`
against a sorted first entry of `blog/ar/git-diff-...`), which is what makes the
twin's order a property of this filesystem and not a contract either side could
be held to.

NORMALISED COMPARISON, and exactly what was normalised: RECORD ORDER, nothing
else. stdout is consecutive (`Pattern:`, `Line:`) PAIRS, so it was chunked into
pairs and the multiset compared; stderr's three header lines and its summary line
are positional and were compared IN PLACE, with only the warning block between
them compared as a multiset.

    corpus size:      1107 files on both sides (the same number, so nothing
                      silently grew or shrank across the cutover)
    stdout records:   6 on each side, multisets EQUAL,
                      normalised sha256 c0a46a831b45abee... on BOTH
    stderr header:    identical in place, "✓ Scanning 1107 content files..."
    stderr summary:   identical in place, "⚠ 6 warning(s) (review recommended)"
    stderr warnings:  6 on each side, EQUAL as a multiset, unequal in order

So the VERDICT, the corpus, the finding set and the exit code all agree, and the
print order does not. A reader deciding whether to flip the registry on this row
should know that "byte-identical stdout" is NOT true here, which is why it is the
first thing this section says.

DRIVEN RED AS WELL, and the red side IS byte-identical, because the twin takes
FILE ARGUMENTS (`check-content-quality.sh:283`) and so does the port
(content_quality.py:476), so naming one fixture file removes enumeration from the
comparison entirely. The plant is a two-line addition to a copy of a clean
fixture document.

THE CONTROL WAS PROVED BEFORE EITHER SIDE RAN: the clean fixture was driven first
and exited 0, and the planted line was confirmed to sit OUTSIDE the frontmatter
and OUTSIDE any fence, which are the two exemptions that would have made the
plant invisible while looking like a gate that could not fail.

    both sides -> exit 1, stdout BYTE-IDENTICAL (114 bytes,
    sha256 f8d2b4fd9f3f4925...), stderr BYTE-IDENTICAL (500 bytes,
    sha256 d6f40d57d0428cd4...):

    Pattern: "at its core"
    ✗ .../planted.md:7
    ✗ 1 content quality violation(s) found

THE REAL TREE WAS NEVER WRITTEN TO for this gate.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-content-quality.sh` is NOT deleted
here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Check content for AI slop patterns
needs: none
selftest: true
lane: quality-content
`slow: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import content_quality

if __name__ == "__main__":
    raise SystemExit(content_quality.main(sys.argv[1:]))
