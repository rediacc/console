# PLAN: a staged-files shape-duplication probe at pre-bash, on a cached index
Status: executing
Owner: d778be9d
Updated: 2026-09-20

Scope: `scripts/gates/check-shape-duplication.ts`, `.claude/rediacc_hooks/guards/`, `.claude/hooks/stop/wl_shapedup.py`, `.ci/rediacc_ci/tests/`, `scripts/data/hook-inventory-baseline.json`.

The operator's ruling (see `agent/PLAN-consolidation-pressure.md`) is a synchronous pre-bash check of the STAGED files only, against a cached index of the whole tree, within about 200 ms, failing OPEN and LOUD when the cache is stale. This plan records the mechanism a Plan agent designed after measuring it, and the reasons the obvious alternatives were rejected.

## The design problem

The cache holds the tree's window hashes, but a staged file is new bytes, and hashing it needs the gate's `normalise` and `stripNoise` (`check-shape-duplication.ts:360`, `:253`). A Python guard that reimplemented them would be a second implementation of one decision, the class of the four incidents in the consolidation plan. `isSharedHelperCall` also derives its helper set from the
whole corpus, so the normalization cannot be ported by reading a regex.

## Mechanism

The gate's own exported functions run inside a small pre-bundled `.mjs`, built from the same source that produced the index. The Python guard spawns it only when a corpus file is staged. `normalise`, `windows` and the counting rule are then one implementation reached by two entry points, and nothing is left to disagree except the cache contents, which an agreement test pins.

Measured on this machine (Node 22, Python 3.14): `npx tsx` cold start 0.96 to 1.7 s and `node --import tsx` 0.28 s, both over budget; an esbuild bundle of the gate runs in 58 to 73 ms, about 115 ms with the largest corpus file normalised. `git diff --cached --name-only` and `git ls-files -s` over the four corpus pathspecs take about 5 ms each, and parsing a 143 KB index in Python
takes under 1 ms. The full corpus scan is 1.2 s over 352 files, so it never belongs on the commit path.

The gate fires when a window hash reaches 3 distinct files, so the index keeps only hashes carried by 2 or more files (1,191 hashes, 180 KB), and a staged file matters only when one of its hashes already has 2 other files. The seed is read at probe time, so a seed edit needs no refresh.

## Files

- `scripts/gates/check-shape-duplication.ts`: export `countShapes` (factored from the loop in `judge`), `kindFor`, `isOptedOut`, `FAMILY_PATHSPECS` and an `ADVICE` constant; make `ROOT` overridable by `--root`; add `--emit-index` and a `probeMain` entry. The floors apply only on the default families, so a broken scan never writes a cache.
- `.ci/cache/shape-index/index.json` and `probe.mjs` (gitignored, written atomically): `schema`, `window`, `n`, `pathspecs`, `inputs` (sha256 of the bundle's import closure from esbuild's metafile), `bundle_sha`, `corpus` (git blob sha per scanned path), `opted_out`, `helpers`, `near`.
- `.claude/rediacc_hooks/guards/warn_staged_shape_duplication.py`: `CHAIN = "pre-bash"`, `TWIN = None`, `ORDER = 42`, never DENY.
- `wl_shapedup.py`: add `--emit-index` to the counter argv it already runs, and bypass the `corpus_sig` early return when the index is missing, so the stop hook refreshes the cache at zero extra cost.
- Registration: `scripts/data/hook-inventory-baseline.json`, plus `test-warn_staged_shape_duplication.py` beside the guard.

## Staleness and loudness

The guard treats any of these as "cannot run" and names the cause: missing, unreadable or corrupt index; unknown schema; the sha256 of any input or of `probe.mjs` differing from the recorded value (the algorithm changed); a corpus path added, removed or changed relative to `git ls-files -s`. HEAD and mtimes are deliberately not keys, since either would invalidate on unrelated
commits or on a checkout.

The guard never denies. "Is this the Nth copy" is a judgement the stop judge already makes with an escape, the probe has known approximation gaps, and the CI gate owns the refusal. A warning must be seen, so it is written to stderr and to stdout as a JSON `systemMessage` plus `additionalContext`; whether a PreToolUse exit-0 JSON reaches the operator is unverified and is the first
thing to confirm live. A wall-clock deadline of 0.3 s covers everything after the command match, with the child in its own process group, and a timeout is a loud allow.

## Tests

A hermetic scratch-repo harness (no cache, corrupt cache, tampered input, altered bundle, drift, more than 12 staged corpus files, no `node`, a slowed probe with a wall bound, `-a` commits, a genuine third copy, an unrelated file). And `.ci/rediacc_ci/tests/test_shape_probe_agreement.py`: for a sample of corpus files, the probe's coalesced findings with that file staged must equal
the gate's own findings (seeding disabled by a new `--no-seed`) that include it, compared as `file:line` sets, with a planted two-file hash proving the control can fail. Gate `--selftest` gains controls for `countShapes` and the near-index selection.

## Known gaps

The helper set is the cached one, so a staged file that newly makes a module shared changes the answer only at CI. `-a` and pathspec commits are skipped with a notice. A `.gitattributes` filter could cause spurious drift, loudly. Unverified: esbuild resolution from `tsx`'s dependency tree, whether the new exports trip a dead-code gate, and the composed end-to-end latency, which the
implementer must measure.

## Tasks

- [ ] Gate edits in `check-shape-duplication.ts` (exports, `--root`, `--emit-index`, `--no-seed`, `probeMain`) with `--selftest` controls
- [ ] The emit step: atomic write of `index.json` and `probe.mjs`, esbuild resolved from `tsx`
- [ ] The guard, its `EDGE_CASES` and `DEFECT`, and its hermetic harness
- [ ] `wl_shapedup.py` refresh trigger and missing-index bypass
- [ ] `test_shape_probe_agreement.py`
- [ ] Register in `hook-inventory-baseline.json`; run `npm run ci:quick`
- [ ] Measure the composed latency and confirm the loud channel live
- [ ] Commit, tick worklist `6ef6d1d1`, tick the box in `agent/PLAN-consolidation-pressure.md`, set this plan `Status: done`
