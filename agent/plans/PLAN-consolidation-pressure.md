# PLAN: Agreement detection and proof obligations for bulk change
Status: compacted
First-Seen: 2026-09-20
Owner: d778be9d
Full-Text-Blob: a6ea9a9a7a15345da735ff30ad88810a8c2125a9
Record-Sig: 959be3c1

## Why
Four incidents escaped detection while all gates were green: duplicate implementations of shared policies diverged (comment vs docstring handling), a constraint existed in one place but wasn't consulted by siblings (REFLOW_STOP), fixes covered only one language or call site while siblings had identical blind spots. The root cause: no mechanism enforced agreement between sibling
implementations. Line-level and diff-level metrics miss policy violations in code that takes different paths to the same decision.

## Outcome
Landed. Switched from duplication detection (insufficient) to agreement detection via executable parity gates generalizing test_guards_differential.py, with shared corpus and per-family COUNT floors. First proof pair registered: python_comment_lines vs _python_reflow_lines. Proof obligations wired into stop judge, pre-bash guards (commit/push/gh write paths). Staged-files
duplication probe designed in agent/plans/PLAN-staged-duplication-probe.md, commit e7d882261. Batch-size-scales-with-proof rule added to docs/agent-reference/TRAPS.md. Family-widening question folded into agent/plans/PLAN-extension-shaped-matchers.md (its commit 3, still in flight).

## Lessons
- Declarative agreement registries go silent when stale; executable parity gates computing both sides on every run stay honest by construction — renamed paths fail, unregistered siblings hit COUNT floors, no allowlist to hide in.
- Duplication detection cannot catch policy divergence between implementations with different bodies making one decision; only agreement detection (differential comparison of outputs) catches non-readers of shared policy.
- A single shared policy home (REFLOW_STOP at line 864) does not guarantee adoption — only a differential between consumers catches a consumer that does not consult it.
- Batch size must scale with proof strength: shape-cluster diff + untouched-scope sweep allows tree-wide changes, AST-proof-only caps to one read-verifiable scope, no proof caps to one file. Automated cleanup on commit is itself a bulk transform and must not bypass proof.
- Sub-agent refactoring contracts must include shape-cluster diff against HEAD with per-cluster counts, results of sweeps over untouched scopes, and exact file ownership — because gates green and tests passing never prove feature correctness.

## Boxes
- [x] Fold the family-widening question into agent/plans/PLAN-extension-shaped-matchers.md commit 3 and remove it from this plan's scope
    (record) sig=b2486512 done=f67f82cca
- [x] Build the sibling-differential harness by generalising the corpus and compare halves of test_guards_differential.py, which stays alive
    (record) sig=2a2b9199 done=f67f82cca
- [x] Register the prose-decision pair as its first entry: python_comment_lines against _python_reflow_lines
    (record) sig=a984dd31 done=f67f82cca
- [x] Register the C-style pair beside it: cstyle_comment_lines against the `.ts`/`.js`/`.go` segment path, which has no region-kind axis and so needs a different coverage signal
    (record) sig=13370e7f done=f67f82cca
- [x] Add a per-family COUNT floor to the pair registry so an unregistered new sibling fails rather than going quiet
    (record) sig=7a215db9 done=f67f82cca
- [x] Write the shape-cluster diff as a reusable script: normalise every changed line to its shape, cluster, diff per-cluster counts against HEAD
    (record) sig=f7d91e90 done=f67f82cca
- [x] Wire the missing-proof refusal into the stop judge, matching the enforcement shape wl_classsweep.py already uses
    (record) sig=a3446cbb done=f67f82cca
- [x] Wire the same refusal into the pre-bash commit, push and gh guards, so the proof is demanded where the change leaves the tree
    (record) sig=419a2340 done=f67f82cca
- [x] Add the pre-bash staged-files-only duplication probe against a cached index, budget 200ms, failing OPEN and LOUD when the cache is stale. Done in `e7d882261`, redesigned Plan-first: see `agent/plans/PLAN-staged-duplication-probe.md`.
    (record) sig=a443e632 done=f67f82cca
- [x] Record the batch-size-scales-with-proof rule in docs/agent-reference/TRAPS.md with a Trap-Id and an Enforced-By pointer
    (record) sig=5b81afb3 done=f67f82cca

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:09:46Z
Boxes: 10 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: none
Gates: none
Why-Source: model
Read-History: `git show a6ea9a9a7a15345da735ff30ad88810a8c2125a9` recovers the text; `git log --find-object=a6ea9a9a7a15345da735ff30ad88810a8c2125a9 --all` names the commit

## History
- 2026-09-20T18:09:46Z compacted by d778be9d from `done` (record-sig 959be3c1)
