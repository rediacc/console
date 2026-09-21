# PLAN: a staged-files shape-duplication probe at pre-bash, on a cached index
Status: compacted
First-Seen: 2026-09-20
Owner: d778be9d
Full-Text-Blob: 69a5cbc721dad210ccc92af94ac69ad7f5860e05
Record-Sig: 681dbbc8

## Why
The consolidation plan required a synchronous pre-bash check of staged files for shape duplication within ~200ms, failing loudly when the cache is stale. The core constraint: staged files need the gate's normalization and helper-detection functions, but reimplementing them in Python would create a second implementation of one decision (the consolidation plan's root problem).

## Outcome
Implemented in commit e7d882261. The gate exports `countShapes`, `kindFor`, `isOptedOut` and builds them into a pre-bundled `.mjs` that the Python guard spawns; one implementation reached by two entry points. The guard is synchronous (~94ms with a corpus file staged, ~9ms without), never denies, and surfaces staleness or cache defects loudly to stderr/stdout as structured messages.

## Lessons
- Pathspec commits (git commit -F file -- paths) needed special handling: probed against the working tree instead of skipped, since they are the only form the pathspecless guard allows.
- The drift check must exclude the committed paths because git ls-files -s reports the index state, not the working tree, and committed changes are not yet reflected there.
- stdin handling requires retry loops for EAGAIN: this is a timing detail that only surfaces under load or concurrent access.
- The cached helper set means a staged file that newly makes a module shared changes the answer only at CI, creating an approximation gap that is acceptable given the gate owns refusal.
- Unverified assumption: whether a PreToolUse exit-0 JSON systemMessage reaches the operator. This was the first thing flagged as needing live confirmation.

## Boxes
- [x] Gate edits in `check-shape-duplication.ts` (exports, `--root`, `--emit-index`, `--no-seed`, `probeMain`) with `--selftest` controls
    (record) sig=2b3ca805 done=f67f82cca
- [x] The emit step: atomic write of `index.json` and `probe.mjs`, esbuild resolved from `tsx`
    (record) sig=03a0fdfa done=f67f82cca
- [x] The guard, its `EDGE_CASES` and `DEFECT`, and its hermetic harness
    (record) sig=917f9086 done=f67f82cca
- [x] `wl_shapedup.py` refresh trigger and missing-index bypass
    (record) sig=b1e665a6 done=f67f82cca
- [x] `test_shape_probe_agreement.py`
    (record) sig=5e32f0dd done=f67f82cca
- [x] Register in `hook-inventory-baseline.json`; run `npm run ci:quick`
    (record) sig=6240d9b4 done=f67f82cca
- [x] Measure the composed latency and confirm the loud channel live
    (record) sig=b29ca7a9 done=f67f82cca
- [x] Commit, tick worklist `6ef6d1d1`, tick the box in `agent/PLAN-consolidation-pressure.md`, set this plan `Status: done`
    (record) sig=bcb9cb4a done=f67f82cca

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:09:24Z
Boxes: 8 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: none
Gates: none
Why-Source: model
Read-History: `git show 69a5cbc721dad210ccc92af94ac69ad7f5860e05` recovers the text; `git log --find-object=69a5cbc721dad210ccc92af94ac69ad7f5860e05 --all` names the commit

## History
- 2026-09-20T18:09:24Z compacted by d778be9d from `done` (record-sig 681dbbc8)
