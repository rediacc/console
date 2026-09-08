#!/usr/bin/env python3
"""Entry point for the ported scope-map reachability gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.scope_scripts_reachability`, which pytest and the
port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8a, the broad tree-scanning nine).
See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port
cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below),
and `python3 -m rediacc_ci.quality.scope_scripts_reachability` works but is the wrong registration
because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to
`[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from
`.ci/scripts/quality/check-scope-scripts-reachability.sh` by an awk range over
its `---- gate ----` block, de-commented, and diffed as an ordered list of whole
lines against the block in this docstring. The twin carried exactly FOUR fields
in this order: `step`, `needs`, `selftest`, `lane`. No `emit:`, no `blocker:`,
no `id:`, no `run:`, no `kind:`, no `why:`.

THE `step:` VALUE IS A KEY, NOT PROSE, and all four copies of it move together
or none do. `gate-bind` matches a header against the workflow step of that exact
name (`gate-bind.ts:1749`), so the string here, `.github/workflows/ci-quality.yml`,
`scripts/ci-runner/manifest.ts` and `scripts/ci-runner/gates.lock.json` must agree
byte for byte; changing one alone silently unbinds the gate from its step.

It used to carry a U+2014 em dash, carried verbatim on the argument that a KEY is
not authored text. That argument was wrong in one direction: the step NAME is
authored here too, and once `.ci/scripts` entered the em-dash gate's surfaces on
2026-09-08 the port reported two new findings the twin never had -- the header
move had carried the dash into a newly covered file. Renamed to a COMMA in all four
places at once, and `npm run gen:gates-lock` re-derived the lock.

A COMMA AND NOT A COLON, which the first attempt used and which broke every
workflow-reading test in the suite. `- name: Scope map: reachable ...` is not
valid YAML: an unquoted scalar cannot contain `: `, so PyYAML refused the whole
file and 23 tests failed on a workflow they could no longer parse. The separator
in a step NAME has to be one that survives being unquoted.

`needs: node` IS THE ONE NON-EMPTY NEED IN THIS BATCH, and it is the field the
brief singles out. The twin's body shells out to node, so `inferredNeeds` may
add `node` for the twin on top of the declaration; this two-import Python entry
point infers NOTHING, because `inferredNeeds` strips Python docstrings as prose
(`gate-header.ts:301`). Carrying the DECLARED `needs: node` is what keeps the
resolved set equal across the move, and the equality was verified by calling
`bind()` on both files and comparing every bound field except `file` and `run`,
not by reasoning about it.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename
to `check:ci-scope-scripts-reachability`, which is the manifest id.

`selftest: true` is inert for a `.py` gate (`gate-bind.ts:598`) and is carried
because the twin declared it and because
`scope_scripts_reachability.main(["--selftest"])` exits 0.

PINNED BY PATH IN ONE HARNESS, and it is a DIFFERENTIAL.
`.ci/rediacc_ci/tests/test_quality_scope_scripts_reachability.py:36` sets
`TWIN = ".ci/scripts/quality/check-scope-scripts-reachability.sh"` and MUST KEEP
NAMING THE TWIN: repointing it makes the port compare with itself. Nothing under
`.ci/scripts/test/gates/` names this gate at all.

THIS ENTRY POINT IS INSIDE THIS GATE'S OWN SUBJECT, checked rather than assumed.
The gate's question is whether every reachable `scripts/` path forces full CI,
so its corpus is `scripts/`, not `.ci/scripts/quality/`. A file landing here
does not enter that corpus, and the shape line the gate prints is identical on
both sides of the cutover with all nine of this batch's entry points on disk,
which is the behavioural half of that claim.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-scope-scripts-reachability.sh   -> exit 0
    .ci/scripts/quality/check_scope_scripts_reachability.py   -> exit 0
    stdout: BYTE-IDENTICAL, 440 bytes, sha256 b9c59ac9b8d264c3...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

    ✓ every root scripts/ and .ci/scripts/ path reachable from a gated job
      forces full CI
      (294 .ci/scripts and 5 dispatch reference(s) scanned;
       extractor controls fired, so this is not an empty pass)

No normalisation was applied and none was needed; the twin was run TWICE against
an unchanged tree and is byte-stable against itself on both streams. The escapes
match too: the twin colours unconditionally and so does the port.

DRIVEN RED AS WELL, in a `cp -r` fixture root rather than on the real tree. The
fixture carries the twin at its own relative path (so its `$BASH_SOURCE` root is
the fixture), `scripts/`, `.github/workflows/`, the six gated `.ci/scripts/`
directories, `.ci/legacy/` and `run.sh`; the port is aimed at it with
`REDIACC_CI_ROOT`. `cp -r`, zero symlinks in the fixture, verified with
`find -type l`. The clean fixture was driven FIRST and both sides exited 0 with
identical bytes, which is what makes the red below attributable to the plant and
not to the fixture.

The plant is one file, `.ci/scripts/build/__gate_probe_8a.sh`, containing a
single command-position reference `bash scripts/check-embed-credits.ts`.

THE CONTROL WAS PROVED ON ALL THREE OF ITS PRECONDITIONS BEFORE EITHER SIDE RAN,
because a plant that missed any one of them would vanish from the scan rather
than fail it: the probe sits under a directory in `GATED_DIRS`, its target
exists in the fixture (a reference to a nonexistent path is skipped at
check-scope-scripts-reachability.sh:139), and the scope map classifies that
target `reduced`, which is not `full`. The third was measured by calling
`classify` directly, not inferred.

    both sides -> exit 1, stdout EMPTY on both, stderr BYTE-IDENTICAL
    (469 bytes, sha256 7613ca5b620c04da...):

    ✗ 1 path(s) reachable from a gated job do not force full CI:
      scripts/check-embed-credits.ts (referenced from .ci/scripts/build)
      classifies 'reduced', expected 'full'

THE REAL TREE WAS NEVER WRITTEN TO for this gate; `git status --porcelain`
carries no probe file.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-scope-scripts-reachability.sh` is NOT deleted
here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Scope map, reachable scripts/ paths force full CI
needs: node
selftest: true
lane: quality-security
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import scope_scripts_reachability

if __name__ == "__main__":
    raise SystemExit(scope_scripts_reachability.main(sys.argv[1:]))
