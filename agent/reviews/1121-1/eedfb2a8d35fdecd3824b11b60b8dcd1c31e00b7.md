# Review eedfb2a8: feat(preview): preview subscriptions, closed sign-up and previewBuild

Commit: eedfb2a8d35fdecd3824b11b60b8dcd1c31e00b7
Repo: private/account
Branch: 1121-1
Parent: d1c8beb3529618a8079aef530e37562a62e533d8
Patch-Id: eb2586cffcf73d0d8428a7568f7c8d872449d763
Reviewed-At: 2026-11-23T08:46:34Z
Model: claude-haiku-5-5
Cost: $0.0100 USD, 1 call(s), 51.6s
Diff: 43621 bytes, 9 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Adds preview subscriptions, closed preview sign-up and a previewBuild server-info field: new capability.
Dropped: 0
Body-Sig: 0d5e2545d4efe065

## Findings

### eedfb2a8.1 [medium] src/types/env.ts:110
Anchor: in-diff
Claim: PREVIEW_BUILD is `z.string().min(1).optional()` and PREVIEW_NAME rejects '' via its regex, so an empty value (e.g. `PREVIEW_BUILD=` in a deploy env) refuses the whole env on every environment, although the file's own comment says every other env field reads an empty value as unset.
Class: other
Resolution: open

### eedfb2a8.2 [low] src/services/preview-subscription.service.ts:104
Anchor: in-diff
Claim: A preview-namespace row that is active with expiresAt NULL (non-expiring) is given a 7-day end date by extendPreviewSubscriptions, which shortens its validity despite the doc saying it never shortens one; the mint path always sets expiresAt, so this only arises from rows created outside it.
Class: other
Resolution: open
