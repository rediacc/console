# Review dd6dfada: fix(account): catch the on-premise forensics alert intake failure and tighten two intake tests

Commit: dd6dfadaefbfe2c2adea87df94a2959f32a4fc77
Repo: private/account
Branch: 1121-1
Parent: d2ce35d4f3225ec80583360ba656283838291914
Patch-Id: 1d40b0d91e751ada254dfa170ffc9d7618f8c554
Reviewed-At: 2026-11-27T22:35:25Z
Model: claude-haiku-5-5
Cost: $0.0020 USD, 1 call(s), 11.8s
Diff: 3548 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Stops a failed forensics alert from becoming an unhandled rejection, which can crash the on-premise server; no new capability. The commit's Release-Note: none line is arguably understated.
Dropped: 0
Body-Sig: 34fec65e35d4bd78

## Findings

### dd6dfada.1 [low] src/entry/on-premise.ts:363
Anchor: in-diff
Claim: The new catch around runForensicsAlert changes behaviour (a failed alert is logged instead of becoming an unhandled rejection), but this diff adds or changes no test that exercises that catch; the commit message cites an intake test that does not appear in the STAT list, so the claim that it pins the catch cannot be checked from this commit.
Class: missing-control-test
Resolution: open
