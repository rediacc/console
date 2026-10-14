# Review c327fe9e: fix(deps): check:deps --upgrade keeps an exact pin exact

Commit: c327fe9eaabcc96d6857c8e1baeca7f0ec29c789
Repo: console
Branch: 1008-1
Parent: 7cf6033c451ecf58d88512e33c9ea68bba3a39d1
Patch-Id: 5155bcf1b57da388ca00118fcae00121a8372c48
Reviewed-At: 2026-10-14T09:39:38Z
Model: claude-haiku-5-5
Cost: $0.0024 USD, 1 call(s), 15.6s
Diff: 5374 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes the dev gate's --upgrade so exact pins stay exact; internal tooling fix with no product API change.
Dropped: 0
Body-Sig: b015a0b6035162b3

## Findings

### c327fe9e.1 [medium] scripts/gates/check-deps.ts:1716
Anchor: in-diff
Claim: The new comment says 'RANGE STYLE IS KEPT', but the non-exact branch still runs plain `npm install name@x`, which rewrites a declared `~x` or `>=x` range to `^x`. The comment misstates what the code does for every range that is not an exact pin.
Resolution: fixed 353cfbfb58ec27ae250b7f713f7001ce082e1cb6 | d778be9d 2026-10-14T11:13:01Z

### c327fe9e.2 [low] scripts/gates/check-deps.ts:1717
Anchor: in-diff
Claim: The new exact/ranged split has no selftest case for a tilde or other non-caret range. The fixture covers only an exact pin and a caret range, so a regression in how the non-exact branch handles those ranges would pass the selftest.
Resolution: fixed 353cfbfb58ec27ae250b7f713f7001ce082e1cb6 | d778be9d 2026-10-14T11:13:02Z
