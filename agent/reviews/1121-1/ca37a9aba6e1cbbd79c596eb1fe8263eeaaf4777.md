# Review ca37a9ab: fix(cli): backup verify prints the records its failure points at, and the LM9 live test runs through rdc.sh with a named machine

Commit: ca37a9aba6e1cbbd79c596eb1fe8263eeaaf4777
Repo: console
Branch: 1121-1
Parent: ba7d42f328cffb7f6e183ced97e6cc9c92347d4d
Patch-Id: 23bea6e2f5dd967c0c2f3bef5305149f10448d92
Reviewed-At: 2026-11-27T07:22:11Z
Model: claude-haiku-5-5
Cost: $0.0087 USD, 1 call(s), 23.9s
Diff: 90598 bytes, 3 files, truncated: yes
Unreviewed: packages/cli/src/commands/backup-storage.ts
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Verify failure now prints the captured records to stderr before the failure; a user-visible CLI fix.
Dropped: 0
Body-Sig: 799748edd7affe37

## Findings

### ca37a9ab.1 [medium] packages/cli/src/commands/__tests__/backup-storage.test.ts:205
Anchor: in-diff
Claim: process.stderr.write is spied in the 'defaults to level=spot' test and restored only by `stderrWrite.mockRestore()` at the end of the body; if any expect above it fails, the spy is never restored and stderr stays mocked for later tests in the file, since afterEach only resets exitCode and vi.clearAllMocks does not restore spies.
Class: seam-not-restored
Resolution: fixed 8fc1b63c19456ad46e2eec476839db2889c6c8b9 | d778be9d 2026-11-27T07:43:54Z

### ca37a9ab.2 [medium] packages/cli/src/commands/mcp/__tests__/stdio-live.test.ts:99
Anchor: in-diff
Claim: The commit says the LM9 test 'refuses to run without' REDIACC_LIVE_MACHINE, but the MACHINE check is only an expect inside the first it(); the second it() still runs and sends repo_list with machine undefined, so the live scenario proceeds without a machine and only fails on the list call.
Class: doc-contradicts-code
Resolution: fixed 3a936f9587d3aabb0c641ef32395367b452e67f6 | d778be9d 2026-11-27T07:43:55Z

### ca37a9ab.3 [low] packages/cli/src/commands/__tests__/backup-storage.test.ts:1
Anchor: in-diff
Claim: Nearly the whole file is re-quoted and re-wrapped (single to double quotes, reflowed calls), so the 576/266-line diff hides the few real test changes and makes the new verify-order assertions hard to review.
Class: other
Resolution: not-a-bug | effe16ca1e restored the single-quote layout; packages/cli/src/commands/__tests__/backup-storage.test.ts:1 | d778be9d 2026-11-27T07:43:55Z
