# Review dffdcec4: chore(plans): tick batch for AP2, AP5, AP8, CF9, LT1 and bench investigation rows

Commit: dffdcec4b35f7b3e345c03d5d8dbc2f55aba0af7
Repo: console
Branch: 1121-1
Parent: 0cb79d5fca41017c4f9c434a4de839e981799c5e
Patch-Id: 798332f1ed333fd28cdf6f3a81ebc023357f70dd
Reviewed-At: 2026-11-25T00:52:16Z
Model: claude-haiku-5-5
Cost: $0.0038 USD, 1 call(s), 14.9s
Diff: 40028 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=docs why=Plan-ledger markdown only: ticks boxes and updates the INDEX.md counts; no code, config or user-facing change.
Dropped: 0
Body-Sig: 2a09b058e150d4c2

## Findings

### dffdcec4.1 [low] agent/plans/PLAN-console-confirm-stepup.md:111
Anchor: in-diff
Claim: CF9 is ticked [x] but its Accept line (line 110) requires both `npm run check:i18n` and `npm run check:ci-i18n-account-key-usage` to return rc 0; the tick cites only check:i18n rc 0, so the second gate has no recorded evidence.
Class: other
Resolution: open

### dffdcec4.2 [low] agent/plans/PLAN-enterprise-tenants.md:214
Anchor: in-diff
Claim: LT1 is ticked [x] on the strength of V4 passing, yet its Accept command (`./run.sh enterprise proof routing --bench`) was never run for LT1 itself; the tick reasons the conditional box is moot rather than recording a rc 0 run, which a reader of the Accept line would not expect.
Class: other
Resolution: open
