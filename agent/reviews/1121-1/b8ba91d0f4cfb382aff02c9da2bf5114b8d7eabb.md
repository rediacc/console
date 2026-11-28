# Review b8ba91d0: fix(forensics): retry unmailed delivery rows and state the orphan watermark behaviour

Commit: b8ba91d0f4cfb382aff02c9da2bf5114b8d7eabb
Repo: private/account
Branch: 1121-1
Parent: c07e6703e7f434829cc2cf678075212481a75ce9
Patch-Id: b9b66e4de045fca910265a61c39ab0f2a69e984d
Reviewed-At: 2026-11-26T09:25:32Z
Model: claude-haiku-5-5
Cost: $0.0050 USD, 1 call(s), 32.4s
Diff: 12058 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes a crash-retry gap and a doc comment in forensics alert delivery; no new user-facing capability.
Dropped: 0
Body-Sig: d218747d8352df5a

## Findings

### b8ba91d0.1 [medium] src/services/forensics-alert.service.ts:515
Anchor: in-diff
Claim: The silent-collector branch of retryPayload (parsing `silent:<sub>:<machine>:<iso>` with slice(0,-25) and slice(-24)) has no test; the new crash test only covers a real finding, so a wrong slice offset would send a mail with a wrong repoGuid or timestamp without failing the suite.
Class: missing-control-test
Resolution: fixed 03fd2c34031627c373ad44f9a4b24ac94489397b | d778be9d 2026-11-26T11:17:01Z

### b8ba91d0.2 [low] src/services/forensics-alert.service.ts:489
Anchor: in-diff
Claim: A row that intake held back by mailAllowed (per-repo 6h window or org daily cap) is now mailed by the retry once that limit lapses within the hour, a behaviour change that the added tests do not exercise (the control test only covers a mailed row and a stale row).
Class: missing-control-test
Resolution: fixed 03fd2c34031627c373ad44f9a4b24ac94489397b | d778be9d 2026-11-26T11:17:01Z
