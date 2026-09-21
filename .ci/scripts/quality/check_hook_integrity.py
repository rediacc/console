#!/usr/bin/env python3
"""Entry point for the ported hook-integrity gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.hook_integrity`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8a, the broad tree-scanning nine). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.hook_integrity` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-hook-integrity.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly SIX fields in this order: `step`, `emit`, `blocker`, `needs`, `selftest`, `lane`. No `id:`, no `run:`,
no `kind:`, no `why:`. The `blocker:` is byte for byte the twin's and is NOT the shared boilerplate the other `emit: false` gates carry: this one names a reason specific to this gate, that its subject IS the setup path, so gating it on setup succeeding would silence the gate that explains a broken setup. A blocker replaced by a lookalike is the same loss as a blocker deleted.

`emit: false` IS CONFIRMED BY ARITHMETIC, not by trusting the field: the step is hand-written at ci-quality.yml:662 and the `quality-code` gate-bind region runs 739-916, so 662 is outside it.

THIS IS THE ONE ROW IN THE BATCH WITH A HAND-WRITTEN STEP THAT NAMES THE TWIN BY
PATH. ci-quality.yml:663 reads `run: .ci/scripts/quality/check-hook-integrity.sh` rather than going through `npm run`. `gate-bind` matches a step by NAME only (`gate-bind.ts:1749`) and never reads its `run:` line, so after the registry is flipped that step stays green while CI keeps executing the TWIN. Every file under `.github/workflows/` was grepped for this basename and 663 is
the only hit. The workflow is not this writer's file; the edit is called out in the report so the driver makes it in the same change.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-hook-integrity`, which is the manifest id.

`selftest: true` is inert for a `.py` gate (`gate-bind.ts:598`) and is carried because the twin declared it and because `hook_integrity.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files. Both infer `[]` and both resolve to the empty set `needs: none` declares.

ITS `paths:` DOES NOT SELECT THIS NEW LEAF, and this is the batch's only instance of the shape that caught `check:ci-shell-size` on 2026-09-08. The manifest entry lists `.ci/scripts/quality/check-hook-integrity.sh` literally, alongside `.claude/hooks/**` and three `scripts/data/*.json` files. A literal is not a glob, so once the leaf becomes `check_hook_integrity.py` the gate's own
implementation stops selecting the gate under `--changed`: editing the gate would no longer run the gate. The manifest is the driver's file; the required edit is named in the report.

PINNED BY PATH IN ONE PLACE, and it is a DIFFERENTIAL. `.ci/rediacc_ci/tests/test_quality_hook_integrity.py:33` sets
`TWIN = paths.from_root(".ci", "scripts", "quality", "check-hook-integrity.sh")`
and MUST KEEP NAMING THE TWIN. Nothing under `.ci/scripts/test/gates/` names this gate.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-hook-integrity.sh   -> exit 0
    .ci/scripts/quality/check_hook_integrity.py   -> exit 0
    stdout: BYTE-IDENTICAL, 1510 bytes, sha256 d0fb260df18165d3...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

    ✓ hook integrity: 43 guard(s) present across 3 chain(s), none newly
      uncovered.

No normalisation was applied and none was needed; the twin was run TWICE against an unchanged tree and is byte-stable against itself on both streams. Neither side emits colour to a redirected stream here, because this twin gates its escapes on `[ -t 1 ]` (check-hook-integrity.sh:103) rather than assigning them unconditionally, and the port agrees.

DRIVEN RED AS WELL, in a `cp -r` fixture root rather than on the real tree, since this gate has no input override. The fixture carries the twin at its own relative path (so its `$BASH_SOURCE` root is the fixture), the three
`scripts/data/hook-*.json` files, `.claude/hooks/` and `.claude/rediacc_hooks/`;
the port is aimed at it with `REDIACC_CI_ROOT`. `cp -r`, and `find -type l` confirms ZERO symlinks in the fixture, for the reason `mutate-check.sh:122` records. The clean fixture was driven FIRST and both sides exited 0 with identical bytes.

The plant DELETES one guard file from the fixture, `.claude/hooks/post-bash/cancel-old-ci.sh`.

THE CONTROL WAS PROVED ON BOTH OF ITS PRECONDITIONS BEFORE EITHER SIDE RAN,
because a file that was outside either list would have been deleted with nothing noticing, which is the exact shape of a plant that fails for reasons that say nothing about the gate: the victim is present in `scripts/data/hook-inventory-baseline.json`, and it sits inside a directory declared in `hook-audit-scope.json`'s `guard_dirs`. The real tree's copy was also re-confirmed
present after the fixture's was removed.

    both sides -> exit 1, stdout BYTE-IDENTICAL (1192 bytes,
    sha256 c5f3edb6ff302228...), stderr BYTE-IDENTICAL (191 bytes,
    sha256 9c4d62ac868d5cf4...):

    ✗ A. guard(s) in the baseline but GONE from the tree:
         .claude/hooks/post-bash/cancel-old-ci.sh
         Removing a guard is a deliberate act: drain the baseline in the same
         commit and say why.

THE VICTIM HAS SINCE BEEN PORTED, and the record above is left as it was driven rather than rewritten, because a rewritten record of a run is not a record. W7 P6 turned `.claude/hooks/post-bash/cancel-old-ci.sh` into `cancel_old_ci.py`, so a re-drive needs a victim that satisfies the same two preconditions TODAY: present in `scripts/data/hook-inventory-baseline.json` and inside
a directory declared in `hook-audit-scope.json`'s `guard_dirs`. `.claude/rediacc_hooks/guards/block_blanket_git_add.py` is one, and `.claude/hooks/trapguard/dispatch.py` is NOT, being in the inventory but in `guards_outside_chains`. The section-A arm the plant exercises is also covered by a live control in this gate's own selftest loop, which is what keeps the assertion running
while this paragraph is only history.

THE REAL TREE WAS NEVER WRITTEN TO for this gate.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-hook-integrity.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Hook integrity
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, and its subject IS the setup path. Emitting it into the region would gate it on setup succeeding, so the gate that explains a broken setup would be the one silenced by it.
needs: none
selftest: true
lane: quality-code
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import hook_integrity

if __name__ == "__main__":
    raise SystemExit(hook_integrity.main(sys.argv[1:]))
