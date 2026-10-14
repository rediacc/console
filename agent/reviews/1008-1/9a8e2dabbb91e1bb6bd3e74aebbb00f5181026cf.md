# Review 9a8e2dab: fix(ci): the ci:quick run-4 reds from the pins and vitest-cache landings, each fixed at its gate

Commit: 9a8e2dabbb91e1bb6bd3e74aebbb00f5181026cf
Repo: console
Branch: 1008-1
Parent: b09f1bdfab9f805f8ccf160495c4cd83149a9fb2
Patch-Id: 3e0d6d5495a8a9380d979ceacfb09d2a18487569
Reviewed-At: 2026-10-14T18:17:10Z
Model: claude-haiku-5-5
Cost: $0.0088 USD, 1 call(s), 32.9s
Diff: 48237 bytes, 25 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=CI and test-config fixes with no user-facing product change; the pins CLI and gate changes are operator and CI tooling only.
Dropped: 0
Body-Sig: eec914f3cd592ca9

## Findings

### 9a8e2dab.1 [medium] scripts/lib/pins/txn.ts:193
Anchor: in-diff
Claim: openJournals now throws whenever the journal root holds any entry, such as a stray .DS_Store or a file, that has no journal.json, because readable stays 0 and the stamps.length > 0 test is true; before, that entry was skipped and an empty list was returned, so any caller of openJournals (a status-type verb) now aborts on such a directory.
Resolution: open

### 9a8e2dab.2 [medium] scripts/lib/pins/drivers/shared.ts:213
Anchor: in-diff
Claim: listFiles now throws a VACUOUS error when a scanned directory yields zero files, where it used to return an empty array; any caller that treats no matches as a legitimate result (an optional directory, a glob that may match nothing) now aborts instead of getting [], and no test in this diff covers that path.
Resolution: open

### 9a8e2dab.3 [medium] scripts/gates/check-ceph-image-pin.ts:50
Anchor: in-diff
Claim: The gate now imports WK_CEPH_IMAGE_REPO from packages/shared/src/config/well-known.generated.js, reaching outside scripts/; literal-sources.json records that a packages/ import made check-ci-parity crash with 'Cannot find module' in bare scripts/-only tree copies, and the same cross-tree import is added to the pins drivers (devcontainer-selftest, embed-selftest, selftest, toolchain-selftest, toolchain), so those harnesses can regress the same way.
Resolution: open

### 9a8e2dab.4 [low] packages/e2e-tests/vitest.config.ts:8
Anchor: in-diff
Claim: The config now calls pathToFileURL(__filename) where the original used import.meta.url; __filename exists only because the config loader injects it, so a direct ESM load of this file would throw a ReferenceError at config time, and import.meta.url was the correct ESM form.
Resolution: open
