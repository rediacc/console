# Review db6aa555: fix(cli-config): keep local edits of a remote cache and let gone-machine repos be removed

Commit: db6aa555ff6c0dc4acaddc0afa2264369dffcdae
Repo: console
Branch: 1104-1
Parent: 000e6cbc3ae97a308da2a79d843e7e388f2a9c4f
Patch-Id: 30f7d1a7eec26bb1b261b484025e8ee17cdcef84
Reviewed-At: 2026-11-06T13:37:47Z
Model: claude-haiku-5-5
Cost: $0.0134 USD, 1 call(s), 47.7s
Diff: 595710 bytes, 64 files, truncated: yes
Unreviewed: packages/cli/src/i18n/locales/es/cli.json, packages/cli/src/i18n/locales/et/cli.json, packages/cli/src/i18n/locales/fr/cli.json, packages/cli/src/i18n/locales/it/cli.json, packages/cli/src/i18n/locales/ja/cli.json, packages/cli/src/i18n/locales/ko/cli.json, packages/cli/src/i18n/locales/pt/cli.json, packages/cli/src/i18n/locales/ru/cli.json, packages/cli/src/i18n/locales/tr/cli.json, packages/cli/src/i18n/locales/zh/cli.json, packages/cli/src/services/__tests__/config-base-remote.test.ts, packages/cli/src/services/__tests__/config-prune-gone-machine.test.ts, packages/cli/src/services/__tests__/config-resources-archive-scrub.test.ts, packages/cli/src/services/config/__tests__/host-local-overlay.test.ts, packages/cli/src/services/config/__tests__/local-edit-guard.test.ts, packages/cli/src/services/config/config-base.ts, packages/cli/src/services/config/config-prune.ts, packages/cli/src/services/config/config-resources.ts, packages/cli/src/services/config/local-edit-guard.ts, packages/cli/src/services/config/machine-gone-repos.ts, packages/cli/src/services/config/push-visibility.ts, packages/cli/src/services/config/resource-state.ts, packages/shared/src/cli-contract/data/contract.generated.ts, packages/shared/src/cli-contract/data/contract.json, packages/shared/src/cli-contract/data/i18n/ar.json, packages/shared/src/cli-contract/data/i18n/de.json, packages/shared/src/cli-contract/data/i18n/en.json, packages/shared/src/cli-contract/data/i18n/es.json, packages/shared/src/cli-contract/data/i18n/et.json, packages/shared/src/cli-contract/data/i18n/fr.json, packages/shared/src/cli-contract/data/i18n/it.json, packages/shared/src/cli-contract/data/i18n/ja.json, packages/shared/src/cli-contract/data/i18n/ko.json, packages/shared/src/cli-contract/data/i18n/pt.json, packages/shared/src/cli-contract/data/i18n/ru.json, packages/shared/src/cli-contract/data/i18n/tr.json, packages/shared/src/cli-contract/data/i18n/zh.json, packages/www/src/content/docs/ar/cli-application.md, packages/www/src/content/docs/de/cli-application.md, packages/www/src/content/docs/en/cli-application.md, packages/www/src/content/docs/es/cli-application.md, packages/www/src/content/docs/et/cli-application.md, packages/www/src/content/docs/fr/cli-application.md, packages/www/src/content/docs/it/cli-application.md, packages/www/src/content/docs/ja/cli-application.md, packages/www/src/content/docs/ko/cli-application.md, packages/www/src/content/docs/pt/cli-application.md, packages/www/src/content/docs/ru/cli-application.md, packages/www/src/content/docs/tr/cli-application.md, packages/www/src/content/docs/zh/cli-application.md, scripts/data/doc-registry.md
Verdict: findings
Attempt: 1
Labels: bump=minor kind=bug,feature why=Fixes repo delete and cleanup for gone machines and adds new --archive-repos and --gone-machine-repos options, all user-facing. Generated docs and i18n are not separate changes.
Dropped: 1
Body-Sig: 5a9a0f7ba6b69e1c

## Findings

### db6aa555.1 [low] packages/cli/src/commands/machine/__tests__/deprovision-repos.test.ts:77
Anchor: in-diff
Claim: The check `toMatch(/obsram:latest, sockfix09b:latest|reposArchived/)` passes on the bare key `reposArchived`, so the test would not catch an archive message that omits the repo names.
Resolution: open

### db6aa555.2 [low] packages/cli/src/commands/machine/__tests__/deprovision-repos.test.ts:83
Anchor: in-diff
Claim: The warn check `toMatch(/obsram:latest|reposLeft/)` and the info check `toMatch(/--gone-machine-repos|reposLeftHint/)` each accept the bare i18n key, so the test does not prove the repos are named or the archive command is shown.
Resolution: open
