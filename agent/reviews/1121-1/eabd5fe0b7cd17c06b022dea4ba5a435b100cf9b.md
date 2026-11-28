# Review eabd5fe0: fix(ci-runner): the 8 build-dependent traces re-run, and the 28 narrowed sets are audited

Commit: eabd5fe0b7cd17c06b022dea4ba5a435b100cf9b
Repo: console
Branch: 1121-1
Parent: fff424346804b4c6117b074cb2f0f5db57a951d0
Patch-Id: 793cda5005c45dbf74c3cd5a17b85b21bf034618
Reviewed-At: 2026-11-25T00:45:10Z
Model: claude-haiku-5-5
Cost: $0.0099 USD, 1 call(s), 55.3s
Diff: 27120 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=CI-runner trace declarations and tooling only; no user-facing change.
Dropped: 0
Body-Sig: 607b902df89701bf

## Findings

### eabd5fe0.1 [low] scripts/ci-runner/path-trace.ts:460
Anchor: in-diff
Claim: The droppedDeclared doc says 'A dropped glob is evidence the trace did not read it', but the function only compares declared globs with git-tracked files (view.files) and never consults the trace's read set, so it cannot establish that.
Class: doc-contradicts-code
Resolution: fixed 9a131ae5a5d737eedc460029a51abe0296b5dbf8 | d778be9d 2026-11-25T01:50:37Z

### eabd5fe0.2 [low] scripts/ci-runner/path-trace.ts:2666
Anchor: in-diff
Claim: The printed message says 'the trace did not read them' for each dropped glob, but droppedDeclared is computed from tracked files and the new declared globs, not from reads, so that statement is never checked; the hedge 'confirm that is true' only partly offsets it.
Class: doc-contradicts-code
Resolution: fixed 9a131ae5a5d737eedc460029a51abe0296b5dbf8 | d778be9d 2026-11-25T01:50:38Z

### eabd5fe0.3 [low] scripts/ci-runner/path-trace.ts:2662
Anchor: in-diff
Claim: The new --replace-declared --write printout (the gate on args.write, args.replaceDeclared and kind 'paths', then the console.error loop) has no selftest; the selftests exercise only the pure droppedDeclared function, so removing the call site would not fail any test.
Class: missing-control-test
Resolution: fixed 9a131ae5a5d737eedc460029a51abe0296b5dbf8 | d778be9d 2026-11-25T01:50:38Z

### eabd5fe0.4 [low] scripts/ci-runner/manifest.ts:3004
Anchor: in-diff
Claim: check:test-workers gets `lists: ['']`, an empty-string list name with no comment (gates.lock.json mirrors it); whatever the hasher does with '' is undocumented, so the gate's input hash may cover the repo root listing without anyone having decided that.
Class: other
Resolution: fixed a88bf8c9a24fb652645d006b32b59492fc872a07 | d778be9d 2026-11-25T01:50:38Z

### eabd5fe0.5 [low] scripts/ci-runner/manifest.ts:2994
Anchor: in-diff
Claim: The entry 'packages/shared/src/config/well-known.generated.ts' is redundant: the 'packages/shared/src/**' glob added at line 2999 already matches it, so the two entries can disagree later without anything noticing.
Class: other
Resolution: fixed a88bf8c9a24fb652645d006b32b59492fc872a07 | d778be9d 2026-11-25T01:50:38Z

### eabd5fe0.6 [low] scripts/ci-runner/trace-ledger.ts:1145
Anchor: in-diff
Claim: The commit says check:ci-go-tool-path and check:ci-pipefail-grep-q were re-traced because they still declare scripts/ops/rebind-code.sh, yet this diff changes no declared path for either gate, only their ledger rows, so the stale declaration the re-trace was meant to address is still there as far as this diff shows.
Class: other
Resolution: not-a-bug | no declaration names scripts/ops/rebind-code.sh any more: git grep -n rebind-code.sh -- scripts/ci-runner/manifest.ts scripts/ci-runner/gates.lock.json prints nothing; removed by c307302404 (the red-gate fixer re-traced both gates after 8cde2fae79 deleted the shim) | d778be9d 2026-11-25T01:54:16Z
