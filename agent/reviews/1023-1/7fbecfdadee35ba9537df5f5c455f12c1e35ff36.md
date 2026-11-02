# Review 7fbecfda: feat(cli): strategy, machine and datastore removal refuse a live reference or cascade on purpose (R5)

Commit: 7fbecfdadee35ba9537df5f5c455f12c1e35ff36
Repo: console
Branch: 1023-1
Parent: 7d12074a21659ccdd12db72efd934b0cdfdf734d
Patch-Id: 6f0740b3022ea27768be5c105899698e00cb3ecb
Reviewed-At: 2026-10-27T02:22:33Z
Model: claude-haiku-5-5
Cost: $0.0092 USD, 1 call(s), 19.6s
Diff: 251185 bytes, 38 files, truncated: yes
Unreviewed: packages/cli/src/i18n/locales/ko/cli.json, packages/cli/src/i18n/locales/pt/cli.json, packages/cli/src/i18n/locales/ru/cli.json, packages/cli/src/i18n/locales/tr/cli.json, packages/cli/src/i18n/locales/zh/cli.json, packages/cli/src/services/__tests__/machine-remove-guard.test.ts, packages/cli/src/services/config/config-datastores.ts, packages/cli/src/services/config/config-strategy-binding.ts, packages/cli/src/services/machine/__tests__/machine-remove-refs.test.ts, packages/cli/src/services/machine/machine-remove-guard.ts, packages/shared/src/cli-contract/data/contract.generated.ts, packages/shared/src/cli-contract/data/contract.json, packages/shared/src/cli-contract/data/i18n/ar.json, packages/shared/src/cli-contract/data/i18n/de.json, packages/shared/src/cli-contract/data/i18n/en.json, packages/shared/src/cli-contract/data/i18n/es.json, packages/shared/src/cli-contract/data/i18n/et.json, packages/shared/src/cli-contract/data/i18n/fr.json, packages/shared/src/cli-contract/data/i18n/it.json, packages/shared/src/cli-contract/data/i18n/ja.json, packages/shared/src/cli-contract/data/i18n/ko.json, packages/shared/src/cli-contract/data/i18n/pt.json, packages/shared/src/cli-contract/data/i18n/ru.json, packages/shared/src/cli-contract/data/i18n/tr.json, packages/shared/src/cli-contract/data/i18n/zh.json
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Adds the --unbind flag and new refusal paths for strategy, machine and datastore removal, which are new user-facing capabilities.
Dropped: 0
Body-Sig: c6d4b38fe3cc7bdd

## Findings

### 7fbecfda.1 [low] packages/cli/src/commands/backup-strategy.ts:424
Anchor: in-diff
Claim: When --destination is passed together with --unbind, the if-branch runs removeBackupDestination and --unbind is silently ignored, with no warning or error and no test covering that combination.
Resolution: fixed e0a0233202480dd6f5488c9135fac5dd4cf7d7e2 | d778be9d 2026-10-27T02:39:11Z
