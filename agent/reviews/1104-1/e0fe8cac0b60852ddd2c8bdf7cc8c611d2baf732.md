# Review e0fe8cac: feat(account): every reminder producer writes a notice; backup and renewal mails in the digest shape

Commit: e0fe8cac0b60852ddd2c8bdf7cc8c611d2baf732
Repo: private/account
Branch: 1104-1
Parent: f25bb641bd0f7d3a7a903e238e45d9c6055aa691
Patch-Id: 56d70a89e45b6427a092a8f7e081941649a31ab3
Reviewed-At: 2026-11-12T07:39:09Z
Model: claude-haiku-5-5
Cost: $0.0126 USD, 1 call(s), 51.7s
Diff: 84343 bytes, 30 files, truncated: yes
Unreviewed: tests/integration/producer-notices.test.ts
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=New notices for every reminder producer and new certExpiring/evalExpiring preferences; user-facing mail and settings change.
Dropped: 0
Body-Sig: db8c3612bf932df8

## Findings

### e0fe8cac.1 [low] src/services/reminder.service.ts:275
Anchor: in-diff
Claim: The eval loop calls noticeService.upsert outside any try (unlike the backup loop, where it is inside one), so a rejected upsert propagates out of the loop and skips every later recipient's mail for that run; they are retried only on the next run.
Class: other
Resolution: fixed be45ed945706c64d52f5babce9d177cac840b72e | d778be9d 2026-11-12T09:08:19Z

### e0fe8cac.2 [low] src/services/reminder.service.ts:345
Anchor: in-diff
Claim: The certificate loop calls noticeService.upsert outside any try, so one rejected upsert aborts the loop and every later certificate holder's mail for that run is deferred to the next run.
Class: other
Resolution: fixed be45ed945706c64d52f5babce9d177cac840b72e | d778be9d 2026-11-12T09:08:19Z

### e0fe8cac.3 [low] src/services/reminder.service.ts:399
Anchor: in-diff
Claim: The renewal loop calls noticeService.upsert outside any try, so one rejected upsert aborts the loop and all later owner/admin recipients are skipped for that run.
Class: other
Resolution: fixed be45ed945706c64d52f5babce9d177cac840b72e | d778be9d 2026-11-12T09:08:19Z

### e0fe8cac.4 [low] src/services/notification.service.ts:45
Anchor: in-diff
Claim: sendTermsNotices awaits opts.notices.upsert before each send with no try, so one rejected upsert throws out of the whole tick and the remaining recipients get no mail until the next hourly tick.
Class: other
Resolution: fixed be45ed945706c64d52f5babce9d177cac840b72e | d778be9d 2026-11-12T09:08:19Z

### e0fe8cac.5 [low] src/email/templates/digest.ts:41
Anchor: in-diff
Claim: The comment says one of subjectKey and fixedSubjectKey is set, but both are optional and nothing enforces it; a caller that sets neither gets t('') as the subject.
Class: doc-contradicts-code
Resolution: fixed be45ed945706c64d52f5babce9d177cac840b72e | d778be9d 2026-11-12T09:08:20Z
