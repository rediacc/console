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
Resolution: fixed 9229986975ca7e75f19ba3c97a8af24855ffa5b7 | d778be9d 2026-10-14T18:36:39Z

### 9a8e2dab.2 [medium] scripts/lib/pins/drivers/shared.ts:213
Anchor: in-diff
Claim: listFiles now throws a VACUOUS error when a scanned directory yields zero files, where it used to return an empty array; any caller that treats no matches as a legitimate result (an optional directory, a glob that may match nothing) now aborts instead of getting [], and no test in this diff covers that path.
Resolution: not-a-bug | scripts/lib/pins/drivers/shared.ts:213-216 throws only when the git listing and the directory walk both find no file at all in the repo; a glob that matches nothing still returns [] (shared.ts:218-219). Callers are scripts/lib/pins/drivers/actions.ts:112, :365, :369 over a scanned repo or '.', never an empty one | d778be9d 2026-10-14T18:36:39Z

### 9a8e2dab.3 [medium] scripts/gates/check-ceph-image-pin.ts:50
Anchor: in-diff
Claim: The gate now imports WK_CEPH_IMAGE_REPO from packages/shared/src/config/well-known.generated.js, reaching outside scripts/; literal-sources.json records that a packages/ import made check-ci-parity crash with 'Cannot find module' in bare scripts/-only tree copies, and the same cross-tree import is added to the pins drivers (devcontainer-selftest, embed-selftest, selftest, toolchain-selftest, toolchain), so those harnesses can regress the same way.
Resolution: not-a-bug | the bare-tree harness copies the registry file next to scripts/: .ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py:172 (copy2 of packages/shared/src/config/well-known.generated.ts), and the same relative import already sits in scripts/gates/check-docker-image-freshness.ts:147; the literal-sources.json crash was for scripts/ci-runner/manifest.ts, which the harness runs without that copy. ch | d778be9d 2026-10-14T18:36:39Z

### 9a8e2dab.4 [low] packages/e2e-tests/vitest.config.ts:8
Anchor: in-diff
Claim: The config now calls pathToFileURL(__filename) where the original used import.meta.url; __filename exists only because the config loader injects it, so a direct ESM load of this file would throw a ReferenceError at config time, and import.meta.url was the correct ESM form.
Resolution: not-a-bug | packages/e2e-tests/package.json:5 has "type": "commonjs", so vitest loads its config as CJS where import.meta.url is the invalid form and __filename is defined; the commit changed it because import.meta.url failed there | d778be9d 2026-10-14T18:36:39Z
