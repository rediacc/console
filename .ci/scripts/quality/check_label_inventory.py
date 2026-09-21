#!/usr/bin/env python3
"""Entry point for the ported label-inventory gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.label_inventory`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8a, the broad tree-scanning nine). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.label_inventory` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-label-inventory.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly FOUR fields in this order: `kind`, `test`, `blocker`, `needs`. No `step:`, no `emit:`, no `id:`, no
`run:`, no `lane:`, no `selftest:`, no `why:`.

`kind: test` IS THE LOAD-BEARING ONE, and the `blocker:` under it is live suppression reason carried byte for byte. Grepped `.github/workflows/` for `check-label-inventory.sh`: ZERO hits, which is what `kind: test` predicts. This gate reaches CI only through `test_gate_label_inventory.py` inside the shared "Python package tests"
step, the bash gate test having been retired in W7 P5, so that blocker is the whole of its CI story and losing a clause of it would be a quiet exemption.

NO `selftest:` IS CORRECT, carried exactly as found: the twin did not declare one, and declaring one here would be a new claim rather than a moved one.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-label-inventory`, which is the manifest id.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files. Both infer `[]` and both resolve to the empty set `needs: none` declares.

PINNED BY PATH IN THREE PLACES, AND THE ROWS SPLIT ACROSS ALL THREE ARMS:

  - RUN-IN-PLACE, so ENTRY POINT if repointed:
    `.ci/rediacc_ci/tests/gates/test_gate_label_inventory.py:48` (`GATE_REL`)
  - GREPS A BEHAVIOURAL NEEDLE, so MODULE if repointed.
    `.ci/rediacc_ci/tests/gates/test_gate_review_labels.py:691,792` reads the
    gate as TEXT and asserts the literal
    `"ci|.ci/scripts/review/claude-review-gate.sh"` and its `bump-none` sibling
    are present in its CREATE_ON_DEMAND table. That needle is not in this
    three-line shim; it is in `.ci/rediacc_ci/quality/label_inventory.py`.
  - DIFFERENTIAL, so it MUST KEEP NAMING THE TWIN:
    `.ci/rediacc_ci/tests/test_quality_label_inventory.py:40`

BECAUSE THIS GATE IS `kind: test`, the first bullet is not cosmetic: the header's `test:` now names the port, so CI executes the port under `check:ci-pytest` rather than leaving the twin as the only side CI runs.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-label-inventory.sh   -> exit 0
    .ci/scripts/quality/check_label_inventory.py   -> exit 0
    stdout: BYTE-IDENTICAL, EMPTY on both sides
    stderr: BYTE-IDENTICAL, 117 bytes, sha256 b16402ca484669a1...

    ✓ label inventory reconciled: 29 declared, 29 live (source: GitHub API);
      names, descriptions and colours all agree

THAT RUN READS THE NETWORK, which is worth saying because a network read is the classic source of an unstable stream. It was byte-stable across two runs of the twin on both streams, and both sides reached the same live list. No normalisation was applied.

DRIVEN RED AS WELL, and the red run is deliberately OFFLINE, through the twin's own two injection seams which the port reads under the same names: `LABEL_INVENTORY_LABELS_FILE` for the declaration file and `LABEL_INVENTORY_LIVE_FILE` for the live list. Removing the network from the comparison is the point: a red that depended on a live read would be a claim about GitHub as much as
about the gate.

THE CONTROL WAS PROVED IN BOTH DIRECTIONS BEFORE THE PLANT RAN. A clean copy of `.github/labels.yml` paired with a 29-name live list exits 0 on the twin, which proves the two seams are not themselves what reds; the planted copy is the same file with exactly ONE label block deleted (`wontfix`), so the declared side carries 28 against a live 29.

    both sides -> exit 1, stdout EMPTY on both, stderr BYTE-IDENTICAL
    (473 bytes, sha256 71a9416aaf582a5c...):

    ✗ label 'wontfix' exists on the repo but is declared nowhere in
      <fixture>. ... Declare it ... or delete it: gh label delete 'wontfix'
    ✗ 1 label inventory mismatch(es)

THE REAL TREE WAS NEVER WRITTEN TO for this gate; `.github/labels.yml` is untouched and the edited copy lives only at a scratch path.

THE TWIN IS GONE: W7 P5 froze `.ci/scripts/quality/check-label-inventory.sh`'s output into `.ci/rediacc_ci/tests/goldens/label-inventory/` and deleted it, so the differential now compares this port against the bytes the twin recorded rather than against a second live implementation.

---- gate ----
kind: test
test: .ci/rediacc_ci/tests/gates/test_gate_label_inventory.py
blocker: BLOCKER: test_gate_label_inventory.py:test_real_tree_reconciles_against_an_injected_live_list runs the gate seam-free over the REAL .github/labels.yml under check:ci-pytest (ci-quality.yml quality-security) with the live list injected, so the real parse, the declared floor and the create-on-demand check execute every CI run; the live GitHub read runs on npm
needs: none
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import label_inventory

if __name__ == "__main__":
    raise SystemExit(label_inventory.main(sys.argv[1:]))
