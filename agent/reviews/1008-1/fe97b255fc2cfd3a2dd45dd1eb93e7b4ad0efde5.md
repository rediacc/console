# Review fe97b255: fix(docs-gen): the json-inventory namer ranks a program before a test, so seven registry rows stop naming a test file as the owner

Commit: fe97b255fc2cfd3a2dd45dd1eb93e7b4ad0efde5
Repo: console
Branch: 1008-1
Parent: fee1fdc33d394a2b87978c4bcd11818177ff2d6b
Patch-Id: 61bad367d4f2acb2e78a5cb103ff7d70f00b6c21
Reviewed-At: 2026-10-08T16:10:43Z
Model: claude-haiku-5-5
Cost: $0.0047 USD, 1 call(s), 21.2s
Diff: 20288 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,docs why=Internal docs-generator ranking fix and regenerated registry; no user-facing change.
Dropped: 0
Body-Sig: 035b923e56a6bcdf

## Findings

### fe97b255.1 [medium] scripts/lib/doc-providers.ts:1801
Anchor: in-diff
Claim: isTestPath matches any basename starting `test-` or `test_` at any depth, so a non-test program such as `scripts/lib/test-runner.ts` would be ranked after programs it should tie with. codeRank then demotes it when it is the only namer of a file, and the registry names a test-ranked or wrong namer for that file.
Resolution: fixed 618e32a174b79ad394380aa7e7ec589098995879 | d778be9d 2026-10-08T16:26:41Z

### fe97b255.2 [low] scripts/lib/doc-providers.ts:1799
Anchor: in-diff
Claim: The new isTestPath/codeRank logic has no unit test. The only guard is a text check on one regenerated registry row (merged-prs.json), so a regression in the `__tests__` or `.test./.spec.` branches would not be caught by the added test.
Resolution: fixed 618e32a174b79ad394380aa7e7ec589098995879 | d778be9d 2026-10-08T16:26:41Z

### fe97b255.3 [low] .ci/rediacc_ci/tests/gates/test_gate_docs_gen.py:343
Anchor: in-diff
Claim: The new test checks only the merged-prs.json row of the regenerated doc-registry.md. The other six reclassified rows in this commit (knip.jsonc, bws-unrequested, secret-reachability, carried-reds, doc-registry-preport, shape-duplication-seed-advisory) have no guard, and a hand-edit of those rows would pass the gate.
Resolution: fixed cc0f8ea7d4d388f082a8725ce2cb592c4bb39690 | d778be9d 2026-10-08T16:36:48Z
